"""ST-chats feature — player->character assignment parsing + per-game storage.

The Storyteller supplies a JSON (via /createstchats) mapping players to their
characters; /assignrole later looks a player up to reveal their role. Character
canonicalization + alignment come from botc_chardata.

Accepted JSON shapes (all normalize the same):
  1. {"players": [ {"name": "...", "character": "...", "alignment": "Good"|"Evil"?}, ... ]}
  2. [ {"name": "...", "character": "...", "alignment": ...?}, ... ]
  3. {"PlayerName": "Character", ...}                (alignment derived from type)
  4. {"PlayerName": {"character": "...", "alignment": ...?}, ...}
`alignment` is optional and only needed to pin a traveler's side.
"""

import os
import re
import json

import botc_chardata

_PATH = ("/home/discord-bot/st_assignments.json" if os.path.isdir("/home/discord-bot")
         else os.path.join(os.path.dirname(os.path.abspath(__file__)), "st_assignments.json"))


def _key(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def parse_assignments(raw):
    """Parse a game JSON (str or decoded) into
        { player_key: {"player": name, "character": canonical, "alignment": "Good"/"Evil"} }
    Returns (assignments, errors)."""
    errors = []
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except Exception as e:
        return {}, [f"Invalid JSON: {e}"]

    rows = None
    if isinstance(data, dict) and isinstance(data.get("players"), list):
        rows = data["players"]
    elif isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = []
        for name, val in data.items():
            if isinstance(val, str):
                rows.append({"name": name, "character": val})
            elif isinstance(val, dict):
                rows.append({"name": name, **val})
    if rows is None:
        return {}, ["Unrecognized JSON shape — expected a players list or a name->character map."]

    assignments = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or row.get("player") or "").strip()
        char = str(row.get("character") or row.get("role") or "").strip()
        if not name or not char:
            errors.append(f"Skipped entry missing name/character: {row}")
            continue
        info = botc_chardata.char_info(char, row.get("alignment"))
        if info is None:
            errors.append(f"Unknown character '{char}' (player '{name}').")
            continue
        assignments[_key(name)] = {
            "player": name,
            "character": info["name"],
            "alignment": info["alignment"],
        }
    return assignments, errors


def _load():
    try:
        with open(_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def set_st_assignments(st_user_id, guild_id, game_number, assignments):
    """Store a Storyteller's assignments keyed by THEIR user id, so /assignrole can
    read them from a DM (where there's no guild context). Records guild+game too."""
    d = _load()
    d[str(st_user_id)] = {"guild": str(guild_id), "game": game_number, "assignments": assignments}
    tmp = _PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, indent=2)
    os.replace(tmp, _PATH)


def get_st_record(st_user_id):
    return _load().get(str(st_user_id))


def get_player(st_user_id, name):
    """Resolve a player (freeform name) to their assignment in the ST's stored game."""
    rec = get_st_record(st_user_id)
    if not rec:
        return None
    a = rec.get("assignments", {})
    k = _key(name)
    if k in a:
        return a[k]
    subs = [v for kk, v in a.items() if k and k in kk]
    return subs[0] if len(subs) == 1 else None


# ---------------------------------------------------------------------------
# OAuth (gdm.join) — create ST-only group DMs
# ---------------------------------------------------------------------------

import html
import secrets

import discord
from discord import app_commands
from urllib.parse import urlencode
import aiohttp
from aiohttp import web

CLIENT_ID = "1291896257476034611"
REDIRECT_URI = "http://localhost:8080/callback"          # /finishstchats (manual code paste)
PUBLIC_REDIRECT_URI = "http://64.23.151.82:8080/callback"  # /addtochat (auto web callback)
CALLBACK_PORT = 8080
_API = "https://discord.com/api/v10"

# Per-player OAuth "add me to my chat" states, keyed by an opaque token that
# rides in the authorize URL's `state` param. Durable: each click yields a fresh
# code, so a stored state stays usable for that player.
_STATE_PATH = ("/home/discord-bot/stchats_addstate.json" if os.path.isdir("/home/discord-bot")
               else os.path.join(os.path.dirname(os.path.abspath(__file__)), "stchats_addstate.json"))


def _auth_url():
    return "https://discord.com/oauth2/authorize?" + urlencode({
        "client_id": CLIENT_ID, "response_type": "code",
        "redirect_uri": REDIRECT_URI, "scope": "gdm.join"})


def _add_auth_url(state):
    """Per-player authorize link for /addtochat — identify (to confirm who joined)
    + gdm.join (to add them), redirecting to the droplet's callback server."""
    return "https://discord.com/oauth2/authorize?" + urlencode({
        "client_id": CLIENT_ID, "response_type": "code",
        "redirect_uri": PUBLIC_REDIRECT_URI, "scope": "identify gdm.join",
        "state": state})


async def _exchange_code(code, redirect_uri=REDIRECT_URI):
    """OAuth code -> user access token. Returns (token_or_None, status, body)."""
    data = {"client_id": CLIENT_ID, "client_secret": os.getenv("CLIENT_SECRET", ""),
            "grant_type": "authorization_code", "code": (code or "").strip(),
            "redirect_uri": redirect_uri}
    async with aiohttp.ClientSession() as s:
        async with s.post(_API + "/oauth2/token", data=data) as r:
            body = await r.json(content_type=None)
            return body.get("access_token"), r.status, body


def _bot_headers():
    return {"Authorization": f"Bot {os.getenv('DISCORD_TOKEN', '')}",
            "User-Agent": "DiscordBot (https://clockbot.local, 1.0)"}


async def _create_group_dm(user_token):
    """Create a group DM containing the token's user. Returns (status, body)."""
    async with aiohttp.ClientSession() as s:
        async with s.post(_API + "/users/@me/channels", headers=_bot_headers(),
                          json={"access_tokens": [user_token]}) as r:
            return r.status, await r.json(content_type=None)


async def _patch_channel(channel_id, body):
    """The bot owns bot-created group DMs, so it can PATCH their name/icon."""
    async with aiohttp.ClientSession() as s:
        async with s.patch(f"{_API}/channels/{channel_id}", headers=_bot_headers(), json=body) as r:
            return r.status, await r.json(content_type=None)


async def _get_me(access_token):
    """Whoever authorized (needs the identify scope). Returns (status, body)."""
    async with aiohttp.ClientSession() as s:
        async with s.get(_API + "/users/@me",
                         headers={"Authorization": f"Bearer {access_token}",
                                  "User-Agent": "DiscordBot (https://clockbot.local, 1.0)"}) as r:
            return r.status, await r.json(content_type=None)


async def _add_recipient(channel_id, user_id, access_token, nick=None):
    """Add a user to a group DM. Bot token in the header (it owns the DM); the
    user's own gdm.join access_token in the body. Returns (status, text)."""
    body = {"access_token": access_token}
    if nick:
        body["nick"] = nick[:32]
    async with aiohttp.ClientSession() as s:
        async with s.put(f"{_API}/channels/{channel_id}/recipients/{user_id}",
                        headers=_bot_headers(), json=body) as r:
            return r.status, await r.text()


# ---------------------------------------------------------------------------
# /addtochat OAuth state store + droplet callback server
# ---------------------------------------------------------------------------

def _load_states():
    try:
        with open(_STATE_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_states(d):
    tmp = _STATE_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, indent=2)
    os.replace(tmp, _STATE_PATH)


def make_add_state(st_user_id, game, key, channel_id, player_id, player_name, character):
    d = _load_states()
    token = secrets.token_urlsafe(16)
    d[token] = {"st_user_id": str(st_user_id), "game": game, "key": key,
                "channel_id": str(channel_id), "player_id": str(player_id),
                "player_name": player_name, "character": character}
    _save_states(d)
    return token


def get_add_state(token):
    return _load_states().get(token)


def _page(title, inner):
    return ("<!doctype html><html><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{html.escape(title)}</title><style>"
            "body{font-family:system-ui,'Segoe UI',Roboto,sans-serif;background:#1e1f22;color:#eee;"
            "display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0;text-align:center}"
            ".card{background:#2b2d31;padding:2.2rem 2.6rem;border-radius:14px;max-width:430px;box-shadow:0 6px 24px #0006}"
            "h1{font-size:1.35rem;margin:.2rem 0 .7rem}p{color:#c7c9ce;line-height:1.5;margin:.5rem 0}"
            "code{background:#1e1f22;padding:.1rem .35rem;border-radius:5px}"
            ".ok{color:#3ba55d}.err{color:#ed4245}</style></head>"
            f"<body><div class='card'>{inner}</div></body></html>")


def _html(title, inner, status=200):
    return web.Response(text=_page(title, inner), content_type="text/html", status=status)


async def _handle_callback(request):
    try:
        code = request.query.get("code")
        state = request.query.get("state")
        if not code or not state:
            return _html("Error", "<h1 class='err'>Incomplete link</h1>"
                         "<p>Ask your Storyteller for a fresh one.</p>", 400)
        rec = get_add_state(state)
        if not rec:
            return _html("Error", "<h1 class='err'>Link expired</h1>"
                         "<p>Ask your Storyteller to run <b>/addtochat</b> again.</p>", 400)
        token, status, body = await _exchange_code(code, PUBLIC_REDIRECT_URI)
        if not token:
            return _html("Error", "<h1 class='err'>Authorization failed</h1>"
                         "<p>That link may have already been used. Click your Storyteller's link again.</p>", 400)
        _, me = await _get_me(token)
        if isinstance(me, dict) and me.get("id") and str(me["id"]) != rec["player_id"]:
            who = html.escape(str(me.get("global_name") or me.get("username") or "another account"))
            return _html("Wrong account",
                         f"<h1 class='err'>That's not your link</h1><p>This invite is for "
                         f"<b>{html.escape(rec['player_name'])}</b>, but you're signed in as <b>{who}</b>. "
                         "Switch to the right Discord account and try again.</p>", 403)
        add_status, add_text = await _add_recipient(rec["channel_id"], rec["player_id"], token, rec["player_name"])
        if 200 <= add_status < 300:
            return _html("You're in!",
                         f"<h1 class='ok'>You're in! ✅</h1><p>You've been added to your Storyteller "
                         f"chat for <b>game {html.escape(str(rec['game']))}</b>.</p>"
                         "<p>Head back to <b>Discord</b> — it's in your Direct Messages.</p>")
        return _html("Couldn't add you",
                     f"<h1 class='err'>Couldn't add you</h1><p>Discord said: "
                     f"<code>{html.escape(add_text[:150])}</code></p><p>Let your Storyteller know.</p>", 400)
    except Exception:
        import traceback
        print("[stchats] callback handler error:"); traceback.print_exc()
        return _html("Error", "<h1 class='err'>Something went wrong</h1>"
                     "<p>Tell your Storyteller to check the logs.</p>", 500)


_web_started = False


async def _start_callback_server():
    global _web_started
    if _web_started:
        return
    # A public port draws constant scanner/HTTP-2 probes that aiohttp logs as
    # unhandled parse tracebacks — silence those so real errors stay visible
    # (our own handler errors are printed by _handle_callback's except block).
    import logging
    logging.getLogger("aiohttp.server").setLevel(logging.CRITICAL)
    app = web.Application()
    app.router.add_get("/callback", _handle_callback)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", CALLBACK_PORT).start()
    _web_started = True
    print(f"[stchats] callback server listening on :{CALLBACK_PORT}")


def _icon_data_uri(character):
    """A character's token as a 128px PNG data URI (flattened on white so the
    transparent token corners don't render black), or None."""
    try:
        p = (botc_chardata.char_info(character) or {}).get("icon")
        if not p or not os.path.exists(p):
            return None
        import io as _io
        import base64 as _b64
        from PIL import Image
        tok = Image.open(p).convert("RGBA")
        bg = Image.new("RGBA", tok.size, (255, 255, 255, 255))
        bg.paste(tok, (0, 0), tok)
        buf = _io.BytesIO()
        bg.convert("RGB").resize((128, 128)).save(buf, "PNG")
        return "data:image/png;base64," + _b64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None


def set_channel_ids(st_user_id, key_to_channel):
    """Record the created group-DM channel id on each player's assignment."""
    d = _load()
    rec = d.get(str(st_user_id))
    if not rec:
        return
    for k, cid in key_to_channel.items():
        if k in rec.get("assignments", {}):
            rec["assignments"][k]["channel_id"] = cid
    tmp = _PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, indent=2)
    os.replace(tmp, _PATH)


def set_player_ids(st_user_id, key_to_pid):
    """Cache a resolved Discord id onto each player's assignment (e.g. after a
    common name is added post-setup and /addtochat resolves it live)."""
    d = _load()
    rec = d.get(str(st_user_id))
    if not rec:
        return
    for k, pid in key_to_pid.items():
        if k in rec.get("assignments", {}):
            rec["assignments"][k]["player_id"] = pid
    tmp = _PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, indent=2)
    os.replace(tmp, _PATH)


def _townsfolk_count(guild):
    role = discord.utils.find(lambda r: r.name.lower() == "townsfolk", guild.roles)
    if role is None:
        return 0
    return sum(1 for m in role.members if not m.bot)


def register(bot):
    import botc_games  # current-game-ST gating + game-number helpers

    async def _boot_callback_server():
        try:
            await _start_callback_server()
        except Exception as e:
            print("[stchats] callback server failed to start:", e)
    bot.add_listener(_boot_callback_server, "on_ready")

    @bot.tree.command(name="createstchats",
                      description="Store player→character JSON, then create ST-only group DMs (one per player).")
    @app_commands.describe(file="A .json file of player→character assignments.",
                           text="…or paste the JSON here instead.")
    async def createstchats(interaction: discord.Interaction,
                            file: discord.Attachment = None, text: str = None):
        if interaction.guild is None or not botc_games.is_current_game_st(interaction):
            await interaction.response.send_message(
                "Only the **current game's Storyteller** can use this (in the server).", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        raw = None
        if file is not None:
            try:
                raw = (await file.read()).decode("utf-8", "replace")
            except Exception as e:
                await interaction.followup.send(f"Couldn't read the file: {e}", ephemeral=True)
                return
        elif text:
            raw = text
        if not raw:
            await interaction.followup.send("Give me a JSON **file** or **text** of assignments.", ephemeral=True)
            return
        assignments, errors = parse_assignments(raw)
        if not assignments:
            await interaction.followup.send("No valid assignments parsed.\n" + "\n".join(errors[:8]), ephemeral=True)
            return
        num = botc_games.game_number_from_name(getattr(interaction.channel, "name", "") or "")
        if num is None:
            num = botc_games.latest_game_number(interaction.guild)
        # Resolve each player to a Discord account, so /addtochat can auto-add + DM them.
        unresolved = []
        for pa in assignments.values():
            member, _e = botc_games.resolve_member(interaction.guild, pa["player"])
            if member is not None:
                pa["player_id"] = str(member.id)
            else:
                unresolved.append(pa["player"])
        set_st_assignments(interaction.user.id, interaction.guild.id, num, assignments)
        msg = [f"✅ Stored **{len(assignments)}** assignments for game **{num}**."]
        if errors:
            msg.append("⚠️ " + "; ".join(errors[:5]))
        if unresolved:
            msg.append("⚠️ Couldn't match a Discord account for: " + ", ".join(unresolved[:8])
                       + " — they can still be revealed via /assignrole but can't be auto-added by /addtochat.")
        msg.append(f"\nReady to create **{len(assignments)}** named group DM(s) — one per player. To do that:")
        msg.append(f"**1.** Authorize here → {_auth_url()}")
        msg.append("**2.** You'll land on a `localhost` page that fails to load — that's expected. "
                   "Copy the **`code`** value out of the address bar.")
        msg.append("**3.** Run **/finishstchats** and paste that code.")
        await interaction.followup.send("\n".join(msg), ephemeral=True)

    @bot.tree.command(name="finishstchats",
                      description="Finish creating the ST group DMs with your authorization code.")
    @app_commands.describe(code="The 'code' value from the redirect URL after authorizing.")
    async def finishstchats(interaction: discord.Interaction, code: str):
        if interaction.guild is None or not botc_games.is_current_game_st(interaction):
            await interaction.response.send_message(
                "Only the **current game's Storyteller** can use this (in the server).", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        token, status, body = await _exchange_code(code)
        if not token:
            await interaction.followup.send(
                f"Authorization failed (HTTP {status}). Codes are single-use and expire fast — "
                f"re-authorize and try again.\n`{str(body)[:250]}`", ephemeral=True)
            return
        assignments = (get_st_record(interaction.user.id) or {}).get("assignments", {})
        if not assignments:
            await interaction.followup.send("No stored assignments — run **/createstchats** first.", ephemeral=True)
            return
        created, failed, channels = [], [], {}
        for key, pa in assignments.items():
            st_code, jb = await _create_group_dm(token)
            if 200 <= st_code < 300 and isinstance(jb, dict) and jb.get("id"):
                patch = {"name": pa["player"][:100]}                 # name after the player
                icon = _icon_data_uri(pa["character"])               # + character icon
                if icon:
                    patch["icon"] = icon
                await _patch_channel(jb["id"], patch)
                channels[key] = jb["id"]
                created.append(pa["player"])
            else:
                failed.append((pa["player"], f"{st_code}:{str(jb)[:50]}"))
        if channels:
            set_channel_ids(interaction.user.id, channels)
        msg = [f"Created + named **{len(created)}/{len(assignments)}** group DM(s)."]
        if created:
            msg.append("📇 " + ", ".join(created[:25]))
        if failed:
            msg.append("⚠️ Couldn't create: " + ", ".join(p for p, _ in failed[:8]))
            msg.append("Group-DM creation is rate-limited (~10 per ~15 min, shared with your own manual creation) — "
                       "re-run **/finishstchats** with a fresh code after the cooldown for the rest.")
        msg.append("Now run **/addtochat** — it sends each player a one-click link to join their own DM.")
        await interaction.followup.send("\n".join(msg), ephemeral=True)

    @bot.tree.command(name="addtochat",
                      description="Send players a one-click link to join their own ST group DM.")
    @app_commands.describe(player="One player only (optional). Omit to make links for everyone.")
    async def addtochat(interaction: discord.Interaction, player: str = None):
        if interaction.guild is None or not botc_games.is_current_game_st(interaction):
            await interaction.response.send_message(
                "Only the **current game's Storyteller** can use this (in the server).", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        rec = get_st_record(interaction.user.id)
        if not rec:
            await interaction.followup.send("No stored assignments — run **/createstchats** first.", ephemeral=True)
            return
        assignments = rec.get("assignments", {})
        game = rec.get("game", "?")
        if player:
            pa = get_player(interaction.user.id, player)
            if not pa:
                await interaction.followup.send(f"No player matching **{player}**.", ephemeral=True)
                return
            targets = [(k, v) for k, v in assignments.items() if v.get("player") == pa.get("player")] \
                or [(_key(pa["player"]), pa)]
        else:
            targets = list(assignments.items())

        links, dmd, nodm, skipped, resolved_now = [], [], [], [], {}
        for key, pa in targets:
            cid = pa.get("channel_id")
            pid = pa.get("player_id")
            if not pid:  # common name added after /createstchats — resolve it live
                member, _e = botc_games.resolve_member(interaction.guild, pa["player"])
                if member is not None:
                    pid = str(member.id)
                    resolved_now[key] = pid
            if not cid:
                skipped.append(f"{pa['player']} (no group DM — run /finishstchats)")
                continue
            if not pid:
                skipped.append(f"{pa['player']} (no matched Discord account — map them with "
                               "/add-common-name, then rerun)")
                continue
            state = make_add_state(interaction.user.id, game, key, cid, pid, pa["player"], pa["character"])
            link = _add_auth_url(state)
            links.append(f"**{pa['player']}** → {link}")
            member = interaction.guild.get_member(int(pid))
            if member is None:
                nodm.append(pa["player"]); continue
            try:
                await member.send(
                    f"🎭 Your Storyteller set up your private game chat for **game {game}**.\n"
                    f"Click to join it (one-time authorize, then you're in): {link}\n"
                    "Afterwards it'll be in your Direct Messages.")
                dmd.append(pa["player"])
            except Exception:
                nodm.append(pa["player"])

        if resolved_now:  # cache live-resolved ids so this is a one-time cost
            set_player_ids(interaction.user.id, resolved_now)
        if not links:
            await interaction.followup.send(
                "Nothing to send.\n" + ("\n".join(skipped) if skipped else ""), ephemeral=True)
            return
        head = [f"Generated **{len(links)}** join link(s) for game **{game}**."]
        if dmd:
            head.append("📩 DM'd: " + ", ".join(dmd))
        if nodm:
            head.append("⚠️ Couldn't DM (hand them their link below): " + ", ".join(nodm))
        if skipped:
            head.append("⏭️ Skipped: " + "; ".join(skipped))
        head.append("\n**Links** (in case you need to share any by hand):")
        # Ephemeral messages cap ~2000 chars — chunk header + links across followups.
        chunks, cur = [], ""
        for part in head + links:
            if len(cur) + len(part) + 1 > 1900:
                chunks.append(cur); cur = ""
            cur += part + "\n"
        if cur:
            chunks.append(cur)
        for c in chunks:
            await interaction.followup.send(c, ephemeral=True)

    @bot.tree.command(name="assignrole",
                      description="Reveal a player's role in this chat (Storyteller only).")
    @app_commands.describe(name="The player's name, as in the assignments you loaded.")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def assignrole(interaction: discord.Interaction, name: str):
        rec = get_st_record(interaction.user.id)
        if not rec:
            await interaction.response.send_message(
                "You have no stored assignments — run **/createstchats** in your server first.", ephemeral=True)
            return
        pa = get_player(interaction.user.id, name)
        if not pa:
            await interaction.response.send_message(
                f"No player matching **{name}** in your assignments.", ephemeral=True)
            return
        info = botc_chardata.char_info(pa["character"], pa["alignment"])
        align, char = pa["alignment"], pa["character"]
        ability = (info or {}).get("ability", "")
        icon_url = (info or {}).get("icon_url")
        # Visible reveal — a rich embed with the token image pulled from the CDN
        # by URL (NOT an uploaded file): a file attachment would need write access
        # to the group DM, which the app lacks, and Discord silently forces such a
        # response ephemeral. A URL thumbnail rides in the payload, so it stays public.
        color = discord.Color.red() if align.lower() == "evil" else discord.Color.green()
        embed = discord.Embed(title=char,
                              description=f"You are **{align}**.\n\n{ability}",
                              color=color)
        if icon_url:
            embed.set_thumbnail(url=icon_url)
        try:
            await interaction.response.send_message(embed=embed)
        except Exception:
            await interaction.response.send_message(
                f"You are **{align}**. You are the **{char}**.\n{ability}")
        # Ephemeral confirmation for the ST — [G### Character - player].
        await interaction.followup.send(
            f"[G{rec.get('game', '?')} {char} - {pa['player']}]", ephemeral=True)

    @createstchats.error
    @finishstchats.error
    @addtochat.error
    @assignrole.error
    async def _err(interaction: discord.Interaction, error: app_commands.AppCommandError):
        m = f"Error: {error}"
        if interaction.response.is_done():
            await interaction.followup.send(m, ephemeral=True)
        else:
            await interaction.response.send_message(m, ephemeral=True)
