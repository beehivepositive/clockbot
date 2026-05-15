"""Quest UI views.

QuestView        — active-quest list with navigation and cancel.
QuestOfferView   — offer a single quest (accept / decline).
QuestOfferList   — paginated list of available quests from a pool (village / bounty board).
QuestSwapView    — when player is at max quests and a merchant offers one; lets them
                   pick which active quest to cancel to make room, or decline.
"""
from __future__ import annotations

import discord

from dwarf_explorer.game.quests import (
    get_active_quests, render_quest_summary, MAX_PLAYER_QUESTS,
)
from dwarf_explorer.config import WORLD_SIZE, OCEAN_SIZE


def _flip_y(y: int, location_type: str = "overworld") -> int:
    """Convert internal y (0=north) to display y (0=south) for player-facing text."""
    if location_type == "ocean":
        return OCEAN_SIZE - 1 - y
    return WORLD_SIZE - 1 - y


def _custom_id(guild_id: int, user_id: int, action: str) -> str:
    return f"dex:{guild_id}:{user_id}:{action}"


def _sp(guild_id: int, user_id: int, tag: str, row: int) -> discord.ui.Button:
    """Spacer button."""
    return discord.ui.Button(
        style=discord.ButtonStyle.secondary,
        label="​", disabled=True,
        custom_id=_custom_id(guild_id, user_id, f"qsp_{tag}"),
        row=row,
    )


# ── Active Quest List ──────────────────────────────────────────────────────────

class QuestView(discord.ui.View):
    """Shows active quests with prev/next navigation, cancel, and close."""

    def __init__(self, guild_id: int, user_id: int, quest_index: int = 0,
                 confirm_cancel: bool = False):
        super().__init__(timeout=None)
        gid, uid = guild_id, user_id

        # Row 0: Prev | Cancel / Confirm-cancel | Next
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="◀ Prev",
            custom_id=_custom_id(gid, uid, "quest_prev"),
            row=0,
        ))
        if confirm_cancel:
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.danger, label="✖ Confirm Cancel",
                custom_id=_custom_id(gid, uid, "quest_cancel_confirm"),
                row=0,
            ))
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary, label="↩ Keep",
                custom_id=_custom_id(gid, uid, "quest_cancel_back"),
                row=0,
            ))
        else:
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.danger, label="✖ Abandon",
                custom_id=_custom_id(gid, uid, "quest_cancel"),
                row=0,
            ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="Next ▶",
            custom_id=_custom_id(gid, uid, "quest_next"),
            row=0,
        ))

        # Row 1: Set Target | Close
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.primary, label="📍 Set Target",
            custom_id=_custom_id(gid, uid, "quest_set_target"),
            row=1,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="✖ Close",
            custom_id=_custom_id(gid, uid, "quest_close"),
            row=1,
        ))


async def render_quest_list(db, user_id: int, index: int, in_village: bool = False) -> str:
    quests = await get_active_quests(db, user_id)
    if not quests:
        return "📋 **Quests** — You have no active quests.\n\n*Visit a village to find work, or look for a bounty board.*"

    index = max(0, min(index, len(quests) - 1))
    q = quests[index]
    total = len(quests)

    header = f"📋 **Quests** ({total}/{MAX_PLAYER_QUESTS})  —  Quest {index + 1} of {total}\n\n"
    body   = render_quest_summary(q)

    # Show completable hint when in village for fetch/delivery
    subtype = q.get("quest_subtype", "")
    if in_village and subtype in ("fetch", "delivery"):
        body += "\n\n*💬 If you have the required items, interact with the village NPC to turn in.*"
    _loc_type = q.get("location_type", "overworld")
    if subtype == "investigation" and q.get("location_x"):
        body += f"\n\n*📍 Investigate ruins/shrine near ({q['location_x']}, {_flip_y(q['location_y'], _loc_type)})*"
    if q.get("bounty_wx") or q.get("location_x"):
        marker_x = q.get("bounty_wx") or q.get("location_x")
        marker_y = q.get("bounty_wy") or q.get("location_y")
        if subtype == "kill":
            body += f"\n\n*⚔️ Target area marked on map near ({marker_x}, {_flip_y(marker_y, _loc_type)})*"

    return header + body


# ── Quest Offer ───────────────────────────────────────────────────────────────

class QuestOfferView(discord.ui.View):
    """Shown when a single quest is being offered (accept / decline)."""

    def __init__(self, guild_id: int, user_id: int):
        super().__init__(timeout=None)
        gid, uid = guild_id, user_id

        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.success, label="✅ Accept",
            custom_id=_custom_id(gid, uid, "quest_offer_accept"),
            row=0,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.danger, label="✖ Decline",
            custom_id=_custom_id(gid, uid, "quest_offer_decline"),
            row=0,
        ))


def render_quest_offer(q: dict, source_label: str = "") -> str:
    src = source_label or q.get("source_type", "?").replace("_", " ").title()
    lines = [f"📜 **Quest Offered** [{src}]\n"]
    lines.append(f"**{q['title']}**")
    lines.append(q["description"])
    lines.append("")
    if q.get("quest_subtype") == "kill":
        from dwarf_explorer.game.quests import _ENEMY_NAMES
        name = _ENEMY_NAMES.get(q["target_id"], q["target_id"])
        lines.append(f"Objective: Kill **{q['target_count']} {name}**")
    elif q.get("quest_subtype") == "fetch":
        from dwarf_explorer.game.quests import _ITEM_NAMES
        name = _ITEM_NAMES.get(q["target_id"], q["target_id"])
        lines.append(f"Objective: Gather **{q['target_count']} {name}**")
    elif q.get("quest_subtype") == "investigation":
        lines.append(f"Objective: Investigate the **{q['target_id']}**")
        if q.get("location_x"):
            _lt = q.get("location_type", "overworld")
            lines.append(f"Location: ({q['location_x']}, {_flip_y(q['location_y'], _lt)})")
    elif q.get("quest_subtype") == "delivery":
        _lt = q.get("location_type", "overworld")
        lines.append(f"Objective: Deliver parcel to **({q['location_x']}, {_flip_y(q['location_y'], _lt)})**")
    lines.append("")
    reward_parts = [f"{q['reward_gold']}🪙", f"{q['reward_xp']}xp"]
    if q.get("reward_item"):
        from dwarf_explorer.config import ITEM_EMOJI
        lines.append(f"Reward: {' + '.join(reward_parts)} + {ITEM_EMOJI.get(q['reward_item'], '📦')}")
    else:
        lines.append(f"Reward: {' + '.join(reward_parts)}")
    return "\n".join(lines)


# ── Quest Pool List (village / bounty board) ──────────────────────────────────

class QuestPoolView(discord.ui.View):
    """List of available quests from a pool; player picks one to accept."""

    def __init__(self, guild_id: int, user_id: int, quest_count: int, selected: int = 0):
        super().__init__(timeout=None)
        gid, uid = guild_id, user_id

        # Row 0: navigation + accept
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="◀",
            custom_id=_custom_id(gid, uid, "qpool_prev"),
            row=0,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.success, label="✅ Accept",
            custom_id=_custom_id(gid, uid, "qpool_accept"),
            row=0,
            disabled=(quest_count == 0),
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="▶",
            custom_id=_custom_id(gid, uid, "qpool_next"),
            row=0,
        ))

        # Row 1: close
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="✖ Close",
            custom_id=_custom_id(gid, uid, "qpool_close"),
            row=1,
        ))


async def render_quest_pool(
    pool: list[dict], active_quests: list[dict], selected: int, source_label: str
) -> str:
    """Render the pool list, skipping quests already active for this player."""
    # Filter out already-accepted quests
    active_ids = {q["quest_id"] for q in active_quests}
    available = [q for q in pool if q.get("id") not in active_ids and q.get("quest_id") not in active_ids]

    if not available:
        return f"📋 **{source_label}**\n\nNo new quests available right now. Check back tomorrow."

    selected = max(0, min(selected, len(available) - 1))
    q    = available[selected]
    total = len(available)

    header = f"📋 **{source_label}**  ({total} quest{'s' if total != 1 else ''} available)\n"
    header += f"Quest {selected + 1} of {total}\n\n"
    return header + render_quest_offer(q, source_label)


# ── Quest Swap View (merchant quest when full) ────────────────────────────────

class QuestSwapView(discord.ui.View):
    """When player has MAX quests and merchant offers one.

    Shows active quests numbered 1–5; player picks one to cancel and swap."""

    def __init__(self, guild_id: int, user_id: int, active_count: int):
        super().__init__(timeout=None)
        gid, uid = guild_id, user_id

        # One button per active quest (up to 5)
        for i in range(min(active_count, 5)):
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.danger, label=f"Cancel #{i + 1}",
                custom_id=_custom_id(gid, uid, f"qswap_{i}"),
                row=0,
            ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="✖ Pass",
            custom_id=_custom_id(gid, uid, "qswap_pass"),
            row=1,
        ))


async def render_quest_swap(active_quests: list[dict], merchant_quest: dict) -> str:
    lines = ["🧑‍💼 **The merchant has a job for you — but your quest log is full!**\n"]
    lines.append(f"*Merchant offer:* **{merchant_quest['title']}** — "
                 f"{merchant_quest['description'][:60]}...\n"
                 f"Reward: {merchant_quest['reward_gold']}🪙 +{merchant_quest['reward_xp']}xp\n")
    lines.append("**Cancel one of your active quests to make room:**\n")
    for i, q in enumerate(active_quests[:5]):
        lines.append(f"**#{i + 1}** {q['title']} ({q.get('quest_subtype','')}) "
                     f"— {q['progress']}/{q['target_count']} done")
    return "\n".join(lines)
