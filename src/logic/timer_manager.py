import logging
import re
import asyncio
from src.utils.humanizer import human_delay

logger = logging.getLogger(__name__)

# Mudae bot ID
MUDAE_BOT_ID = 432610292342587392

# Regex to find "You have X rolls left" - Handles optional bold/underline and singular "roll"
ROLLS_PATTERN = re.compile(r"You have (?:[\*_]+)?(\d+)(?:[\*_]+)? rolls? left", re.IGNORECASE)

# Regex for Rolls in Stock
ROLLS_STOCK_PATTERN = re.compile(r"You have (?:[\*_]+)?(\d+)(?:[\*_]+)? rolls? reset in stock", re.IGNORECASE)

# Regex for Claim Status in $tu
CLAIM_READY_PATTERN = re.compile(r"you (?:[\*_]+)?can(?:[\*_]+)? claim right now!", re.IGNORECASE)
CLAIM_NOT_READY_PATTERN = re.compile(r"you (?:[\*_]+)?can't(?:[\*_]+)? claim for another", re.IGNORECASE)

# Regex for DK and Daily
DK_READY_PATTERN = re.compile(r"(\$dk is ready!|Daily kakera: \*\*ready\*\*|Daily kakera is ready!|\$dk is available!)", re.IGNORECASE)
DAILY_READY_PATTERN = re.compile(r"(Daily: \*\*ready\*\*|\$daily is ready!|Daily is ready!|\$daily is available!)", re.IGNORECASE)

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

    # Check if this message is for US to avoid "State Confusion"
    is_for_us = False
    user_names = [bot.user.name.lower()]
    if bot.user.display_name:
        user_names.append(bot.user.display_name.lower())

    content = ""
    if message.embeds:
        embed = message.embeds[0]
        content = embed.description or ""
        # Mudae puts the username in the author field of the $tu embed
        if embed.author and embed.author.name:
            author_name = embed.author.name.lower()
            if any(name in author_name for name in user_names):
                is_for_us = True
    else:
        content = message.content
        content_lower = content.lower()
        if any(name in content_lower for name in user_names):
            is_for_us = True

    if not is_for_us:
        return False

    # Only return True if it matches actual $tu info, to avoid swallowing rolls
    is_timer_info = False

    # 1. Update Rolls Count
    rolls_match = ROLLS_PATTERN.search(content)
    if rolls_match:
        bot.available_rolls = int(rolls_match.group(1))
        logger.info(f"Updated available rolls: {bot.available_rolls}")
        is_timer_info = True

    # 1b. Update Rolls Reset Stock
    rolls_stock_match = ROLLS_STOCK_PATTERN.search(content)
    if rolls_stock_match:
        bot.rolls_stock = int(rolls_stock_match.group(1))
        logger.info(f"Updated rolls reset stock: {bot.rolls_stock}")
        is_timer_info = True

    # 2. Update Claim Status
    if CLAIM_READY_PATTERN.search(content):
        bot.claim_ready = True
        logger.info("Claim is READY according to $tu.")
        is_timer_info = True
    elif CLAIM_NOT_READY_PATTERN.search(content):
        bot.claim_ready = False
        logger.info("Claim is NOT ready according to $tu.")
        is_timer_info = True

    # 3. Update DK and Daily Ready Flags
    if DK_READY_PATTERN.search(content):
        bot.dk_ready = True
        logger.info("DK is ready according to $tu.")
        is_timer_info = True
    else:
        bot.dk_ready = False

    if DAILY_READY_PATTERN.search(content):
        bot.daily_ready = True
        logger.info("Daily is ready according to $tu.")
        is_timer_info = True
    else:
        bot.daily_ready = False

    if is_timer_info:
        bot.roll_response_event.set()

    return is_timer_info
