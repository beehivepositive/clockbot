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

import discord
from discord import app_commands
from urllib.parse import urlencode
import aiohttp

CLIENT_ID = "1291896257476034611"
REDIRECT_URI = "http://localhost:8080/callback"
_API = "https://discord.com/api/v10"


def _auth_url():
    return "https://discord.com/oauth2/authorize?" + urlencode({
        "client_id": CLIENT_ID, "response_type": "code",
        "redirect_uri": REDIRECT_URI, "scope": "gdm.join"})


async def _exchange_code(code):
    """OAuth code -> user access token. Returns (token_or_None, status, body)."""
    data = {"client_id": CLIENT_ID, "client_secret": os.getenv("CLIENT_SECRET", ""),
            "grant_type": "authorization_code", "code": (code or "").strip(),
            "redirect_uri": REDIRECT_URI}
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


def _townsfolk_count(guild):
    role = discord.utils.find(lambda r: r.name.lower() == "townsfolk", guild.roles)
    if role is None:
        return 0
    return sum(1 for m in role.members if not m.bot)


def register(bot):
    import botc_games  # current-game-ST gating + game-number helpers

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
        set_st_assignments(interaction.user.id, interaction.guild.id, num, assignments)
        msg = [f"✅ Stored **{len(assignments)}** assignments for game **{num}**."]
        if errors:
            msg.append("⚠️ " + "; ".join(errors[:5]))
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
        players = list((get_st_record(interaction.user.id) or {}).get("assignments", {}).values())
        if not players:
            await interaction.followup.send("No stored assignments — run **/createstchats** first.", ephemeral=True)
            return
        created, failed = [], []
        for pa in players:
            st_code, jb = await _create_group_dm(token)
            if 200 <= st_code < 300 and isinstance(jb, dict) and jb.get("id"):
                await _patch_channel(jb["id"], {"name": pa["player"][:100]})  # name it after the player
                created.append(pa["player"])
            else:
                failed.append((pa["player"], f"{st_code}:{str(jb)[:50]}"))
        msg = [f"Created + named **{len(created)}/{len(players)}** group DM(s)."]
        if created:
            msg.append("📇 " + ", ".join(created[:25]))
        if failed:
            msg.append("⚠️ Couldn't create: " + ", ".join(p for p, _ in failed[:8]))
            msg.append("Group-DM creation is rate-limited (~10 per ~15 min, shared with your own manual creation) — "
                       "re-run **/finishstchats** with a fresh code after the cooldown for the rest.")
        msg.append("Add each player to their named DM, then reveal with **/assignrole <player>**.")
        await interaction.followup.send("\n".join(msg), ephemeral=True)

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
        # Visible reveal — everyone in the chat sees this.
        await interaction.response.send_message(
            f"You are **{align}**. You are the **{char}**.\n{ability}")
        # Ephemeral confirmation for the ST — role icon + [G### Character - player].
        icon = (info or {}).get("icon")
        tag = f"[G{rec.get('game', '?')} {char} - {pa['player']}]"
        try:
            if icon and os.path.exists(icon):
                await interaction.followup.send(tag, ephemeral=True, file=discord.File(icon))
            else:
                await interaction.followup.send(tag, ephemeral=True)
        except Exception:
            await interaction.followup.send(tag, ephemeral=True)

    @createstchats.error
    @finishstchats.error
    @assignrole.error
    async def _err(interaction: discord.Interaction, error: app_commands.AppCommandError):
        m = f"Error: {error}"
        if interaction.response.is_done():
            await interaction.followup.send(m, ephemeral=True)
        else:
            await interaction.response.send_message(m, ephemeral=True)
