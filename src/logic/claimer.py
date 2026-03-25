import logging
import discord
import re
from src.utils.humanizer import human_delay

logger = logging.getLogger(__name__)

# Mudae bot ID
MUDAE_BOT_ID = 432610292342587392

# Regex to find kakera value in description (e.g., "507** (worth) **")
KAKERA_PATTERN = re.compile(r"(\d+)\s*\*\*")

async def handle_mudae_message(bot, message):
    """Entry point for processing Mudae bot messages for potential claims or confirmations."""
    if message.author.id != MUDAE_BOT_ID:
        return

    # 1. Check for Confirmation Message
    content = message.content.lower()
    if "married" in content:
        # Check if the bot's own name or display name is mentioned in this marriage confirmation
        user_names = [bot.user.name.lower()]
        if bot.user.display_name:
            user_names.append(bot.user.display_name.lower())
        
        if any(name in content for name in user_names):
            logger.info(f"CLAIM CONFIRMED: Message: '{message.content}'")
            from src.logic.roller import get_current_interval_start
            bot.last_claim_interval_start = get_current_interval_start(bot)

            # Stop any active roll sequence immediately
            if bot.current_rolling_task and not bot.current_rolling_task.done():
                bot.current_rolling_task.cancel()
                logger.info("Active roll sequence cancelled.")
            return

    # 2. Universal Button Clicker (Instant Priority)
    # If Mudae sends a button, it's either a claim or kakera. Just click it!
    if message.components:
        for row in message.components:
            for component in row.children:
                if isinstance(component, discord.Button):
                    logger.info("BUTTON DETECTED! Clicking immediately...")
                    try:
                        # Zero delay for buttons to win the race
                        await component.click()
                        return
                    except Exception as e:
                        logger.error(f"Failed to click button: {e}")

    if not message.embeds:
        return

    embed = message.embeds[0]

    # 3. Parse Name (from Author or Title)
    character_name = "Unknown"
    if embed.author:
        character_name = embed.author.name
    elif embed.title:
        character_name = embed.title

    # 4. Parse Description (Series and Kakera)
    description = embed.description if embed.description else ""
    
    kakera_value = 0
    match = KAKERA_PATTERN.search(description)
    if match:
        kakera_value = int(match.group(1))

    # 5. Decision Logic for Marriage Claims (via Reaction fallback)
    should_claim = check_if_should_claim(bot, character_name, description, kakera_value)
    
    if should_claim:
        logger.info(f"MATCH FOUND: '{character_name}' ({kakera_value} kakera). Attempting reaction claim!")
        await perform_claim(bot, message)

def check_if_should_claim(bot, name, description, kakera_value):
    claiming_cfg = bot.config.get("claiming", {})
    
    # Check wishlist
    wishlist = [w.lower() for w in claiming_cfg.get("wishlist", [])]
    if name.lower() in wishlist:
        logger.info(f"Character '{name}' is in wishlist!")
        return True

    # Check kakera threshold
    min_kakera = claiming_cfg.get("min_kakera", 999999) # Default to high if not set
    if kakera_value >= min_kakera:
        logger.info(f"Character '{name}' value ({kakera_value}) exceeds threshold ({min_kakera})!")
        return True
    
    return False

async def perform_claim(bot, message):
    # Reaction fallback (if buttons were missing)
    # Very small jitter (0.15s to 0.4s)
    await human_delay((0.15, 0.4))
    
    try:
        await message.add_reaction("❤️")
        logger.info("Claimed via reaction!")
    except Exception as e:
        logger.error(f"Reaction failed: {e}")
