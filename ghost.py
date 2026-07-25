"""Ghost (hidden) text-triggered commands — not registered as slash commands, so
they never appear in the / picker. The bot watches on_message for exact triggers.

  /human  ->  posts the captioned "I am a human" GIF (and deletes the trigger).
"""
import os
import discord

BASE = "/home/discord-bot" if os.path.isdir("/home/discord-bot") else os.path.dirname(os.path.abspath(__file__))

# trigger (lowercased, stripped) -> gif filename in BASE
GHOST_GIFS = {
    "/human": "human.gif",
}


def register(bot):
    async def _on_message(message):
        if message.author.bot or message.guild is None:
            return
        trigger = (message.content or "").strip().lower()
        fname = GHOST_GIFS.get(trigger)
        if not fname:
            return
        path = os.path.join(BASE, fname)
        if not os.path.exists(path):
            return
        try:
            await message.channel.send(file=discord.File(path, fname))
        except Exception as e:
            print(f"ghost {trigger} failed: {e}")
            return
        # Delete the trigger message so it reads like a clean command (best-effort).
        try:
            await message.delete()
        except Exception:
            pass

    bot.add_listener(_on_message, "on_message")
