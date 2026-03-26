import logging
import discord
import re
from src.utils.humanizer import human_delay

logger = logging.getLogger(__name__)

# Mudae bot ID
MUDAE_BOT_ID = 432610292342587392

# Regex for kakera in $im output (e.g., "Animanga roulette · **102** 💎")
KAKERA_PATTERN = re.compile(r"(\d+)\s*💎")

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

    # 2. Universal Button Clicker (Single Button Logic)
    # Only click if there is EXACTLY one button (avoids $im navigation/help menus)
    total_buttons = 0
    target_button = None
    if message.components:
        for row in message.components:
            for component in row.children:
                if isinstance(component, discord.Button):
                    total_buttons += 1
                    target_button = component
    
    if total_buttons == 1 and target_button:
        logger.info(f"SINGLE BUTTON DETECTED (Label: {target_button.label})! Clicking immediately...")
        try:
            # Zero delay for buttons to win the race
            await target_button.click()
            # Note: We don't return here because we might still want to react if it's a roll
        except Exception as e:
            logger.error(f"Failed to click button: {e}")

    if not message.embeds:
        return

    embed = message.embeds[0]
    description = embed.description if embed.description else ""
    desc_lower = description.lower()

    # Identify if it's a Roll or an Info ($im) message
    # Character rolls MUST have "claim!" and an image.
    is_roll = "claim!" in desc_lower and embed.image
    # Info messages (like $im) have "Animanga roulette" but no "claim!"
    is_info = "animanga roulette" in desc_lower and not is_roll

    if is_roll:
        character_name = "Unknown"
        if embed.author:
            character_name = embed.author.name
        elif embed.title:
            character_name = embed.title
            
        logger.info(f"ROLL DETECTED: {character_name}")

        # 3. Wishlist Check (Immediate Reaction)
        if is_in_wishlist(bot, character_name):
            logger.info(f"WISHLIST MATCH: {character_name}. Attempting immediate claim!")
            await perform_claim(bot, message)
            return

        # 4. Kakera Check via $im (Not in wishlist)
        logger.info(f"NOT IN WISHLIST: {character_name}. Sending $im to check kakera...")
        bot.pending_kakera_checks[character_name.lower()] = message
        await message.channel.send(f"$im {character_name}")
        return

    if is_info:
        # 5. Process $im Response
        character_name = "Unknown"
        if embed.author:
            character_name = embed.author.name
        elif embed.title:
            character_name = embed.title
        
        char_key = character_name.lower()
        if char_key in bot.pending_kakera_checks:
            original_roll_message = bot.pending_kakera_checks.pop(char_key)
            
            # Extract Kakera from description
            kakera_value = 0
            match = KAKERA_PATTERN.search(description)
            if match:
                kakera_value = int(match.group(1))
            
            claiming_cfg = bot.config.get("claiming", {})
            min_kakera = claiming_cfg.get("min_kakera", 999999)

            if kakera_value >= min_kakera:
                logger.info(f"KAKERA CHECK PASSED: {character_name} has {kakera_value} kakera (Min: {min_kakera}). Claiming original roll!")
                await perform_claim(bot, original_roll_message)
            else:
                logger.info(f"KAKERA CHECK FAILED: {character_name} only has {kakera_value} kakera. Ignoring.")

def is_in_wishlist(bot, name):
    claiming_cfg = bot.config.get("claiming", {})
    wishlist = [w.lower() for w in claiming_cfg.get("wishlist", [])]
    return name.lower() in wishlist

async def perform_claim(bot, message):
    # Reaction fallback (if buttons were missing or failed)
    # Small jitter (0.15s to 0.4s)
    await human_delay((0.15, 0.4))
    
    try:
        await message.add_reaction("❤️")
        logger.info("Claimed via reaction!")
    except Exception as e:
        logger.error(f"Reaction failed: {e}")
