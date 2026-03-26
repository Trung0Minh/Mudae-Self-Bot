import logging
import re
import asyncio
from src.utils.humanizer import human_delay

logger = logging.getLogger(__name__)

# Mudae bot ID
MUDAE_BOT_ID = 432610292342587392

# Regex to find "You have X rolls left"
ROLLS_PATTERN = re.compile(r"You have \*\*(\d+)\*\* rolls left")

# Regex for Claim Ready
CLAIM_READY_PATTERN = re.compile(r"(you can claim right now!|Your next claim is ready!|Married: \*\*ready\*\*)")
CLAIM_NOT_READY_PATTERN = re.compile(r"(you can't claim for another|Married: \*\*\d+h \d+m\*\*)")

# Regex for DK and Daily
DK_READY_PATTERN = re.compile(r"(\$dk is ready!|Daily kakera: \*\*ready\*\*|Daily kakera is ready!)")
DAILY_READY_PATTERN = re.compile(r"(Daily: \*\*ready\*\*|\$daily is ready!|Daily is ready!)")

async def check_timers(bot):
    """Sends $tu to the target channel to refresh roll count and claim status."""
    channel_id = bot.target_channel_id
    channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
    
    if channel:
        logger.info("Checking timers ($tu)...")
        await channel.send("$tu")

async def handle_timer_response(bot, message):
    """Parses Mudae's $tu response to update bot state."""
    if message.author.id != MUDAE_BOT_ID:
        return False

    # Check if this is a $tu response
    content = ""
    if message.embeds:
        content = message.embeds[0].description or ""
    else:
        content = message.content

    # 1. Update Rolls Count
    rolls_match = ROLLS_PATTERN.search(content)
    if rolls_match:
        bot.available_rolls = int(rolls_match.group(1))
        logger.info(f"Updated available rolls: {bot.available_rolls}")

    # 2. Update Claim Status
    if CLAIM_READY_PATTERN.search(content):
        bot.claim_ready = True
        logger.info("Claim is READY according to $tu.")
    elif CLAIM_NOT_READY_PATTERN.search(content):
        bot.claim_ready = False
        logger.info("Claim is NOT ready according to $tu.")

    # 3. Update DK and Daily Ready Flags (Don't send commands here)
    if DK_READY_PATTERN.search(content):
        bot.dk_ready = True
        logger.info("DK is ready according to $tu.")
    else:
        bot.dk_ready = False

    if DAILY_READY_PATTERN.search(content):
        bot.daily_ready = True
        logger.info("Daily is ready according to $tu.")
    else:
        bot.daily_ready = False

    return rolls_match is not None or "claim" in content.lower()
