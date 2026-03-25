import logging
import re
import asyncio
from src.utils.humanizer import human_delay

logger = logging.getLogger(__name__)

# Mudae bot ID
MUDAE_BOT_ID = 432610292342587392

# Regex to find "You have X rolls left"
ROLLS_PATTERN = re.compile(r"You have \*\*(\d+)\*\* rolls left")
# Regex to find "Daily: ready"
DAILY_PATTERN = re.compile(r"Daily: \*\*(ready)\*\*")

async def check_timers(bot):
    """Sends $tu to the target channel to refresh roll count and daily status."""
    channel_id = bot.target_channel_id
    channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
    
    if channel:
        logger.info("Checking timers ($tu)...")
        await channel.send("$tu")

async def handle_timer_response(bot, message):
    """Parses Mudae's $tu response to update bot state."""
    if message.author.id != MUDAE_BOT_ID:
        return False

    # Check if this is a $tu response (usually contains your username)
    content = ""
    if message.embeds:
        content = message.embeds[0].description or ""
    else:
        content = message.content

    # Check for rolls count
    rolls_match = ROLLS_PATTERN.search(content)
    if rolls_match:
        bot.available_rolls = int(rolls_match.group(1))
        logger.info(f"Updated available rolls: {bot.available_rolls}")

    # Check for Daily ready
    if DAILY_PATTERN.search(content):
        logger.info("Daily is ready! Sending $daily...")
        await human_delay((1.0, 2.0))
        await message.channel.send("$daily")
        # After $daily, we might want to check $tu again to see new rolls
        # but let's keep it simple for now.

    return rolls_match is not None
