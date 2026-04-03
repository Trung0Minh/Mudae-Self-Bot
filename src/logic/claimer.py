import logging
import discord
import re
from src.utils.humanizer import human_delay

logger = logging.getLogger(__name__)

# Mudae bot ID
MUDAE_BOT_ID = 432610292342587392

# Regex for kakera in $im output - looks for "Animanga roulette" followed by the value
KAKERA_PATTERN = re.compile(r"Animanga roulette\D+(\d+)", re.IGNORECASE)

# Regex to detect a character roll (claimable)
ROLL_INDICATOR_PATTERN = re.compile(r"React with any emoji to claim!", re.IGNORECASE)

def identify_roll_owner(bot, message):
    """
    Identifies the owner of a Mudae roll.
    Returns: (user_id_or_name, is_own_roll)
    """
    is_own_roll = False
    user_id = None

    # 1. Check Interaction (for slash commands/buttons)
    if message.interaction:
        user_id = message.interaction.user.id
        logger.debug(f"Owner identified via Interaction: {user_id}")
        if user_id == bot.user.id:
            is_own_roll = True
        return user_id, is_own_roll

    # 2. Check Embed Footer (for standard and slash rolls)
    if message.embeds and message.embeds[0].footer and message.embeds[0].footer.text:
        footer_text = message.embeds[0].footer.text.strip()
        footer_lower = footer_text.lower()
        
        # SKIP "Belongs to" - This is the character owner, NOT the person who rolled.
        if "belongs to " in footer_lower:
            logger.debug(f"Skipping 'Belongs to' footer: {footer_text}")
        else:
            # Check against our own name/display name
            user_names = [bot.user.name.lower()]
            if bot.user.display_name:
                user_names.append(bot.user.display_name.lower())
            
            if any(name in footer_lower for name in user_names):
                is_own_roll = True
                user_id = bot.user.id
                return user_id, is_own_roll
                
            # Pattern A: "Roll by Username"
            if "roll by " in footer_lower:
                user_id = footer_text.split("roll by ")[1].strip()
                return user_id, is_own_roll
                
            # Pattern B: Just "Username" (Common in Slash Commands)
            # We ignore footers that look like roll counts (e.g., "1/10" or "15 rolls left")
            if not any(x in footer_lower for x in ["/", "rolls left", "roll left"]):
                # If it's a single word or short phrase, it's likely the username
                user_id = footer_text
                logger.debug(f"Owner identified via raw Footer: {user_id}")
                return user_id, is_own_roll
        
        logger.debug(f"Footer did not yield owner: '{footer_text}'")

    # 3. Final Fallback: If we are the ones rolling
    if bot.current_rolling_task and not bot.current_rolling_task.done():
        is_own_roll = True
        user_id = bot.user.id
        return user_id, is_own_roll

    return user_id, is_own_roll

async def handle_mudae_message(bot, message):
    """Entry point for processing Mudae bot messages for potential claims or confirmations."""
    if message.author.id != MUDAE_BOT_ID:
        return

    # 1. Check for Confirmation Message
    content = message.content.lower()
    if "married" in content:
        user_names = [bot.user.name.lower()]
        if bot.user.display_name:
            user_names.append(bot.user.display_name.lower())
        
        if any(name in content for name in user_names):
            logger.info(f"CLAIM CONFIRMED: Message: '{message.content}'")
            from src.logic.roller import get_current_interval_start
            bot.last_claim_interval_start = get_current_interval_start(bot)

            # Stop any active roll sequence immediately, UNLESS we are in the middle of a divorce sequence
            if bot.current_rolling_task and not bot.current_rolling_task.done():
                if not bot.is_divorcing:
                    bot.current_rolling_task.cancel()
                    logger.info("Active roll sequence cancelled.")
                else:
                    logger.info("Claim confirmed during divorce sequence. Not cancelling task.")
            return

    # 2. Universal Button Clicker (Single Button Logic)
    # Click immediately if there is exactly one button
    total_buttons = 0
    target_button = None
    if message.components:
        for row in message.components:
            for component in row.children:
                if isinstance(component, discord.Button):
                    total_buttons += 1
                    target_button = component
    
    if total_buttons == 1 and target_button:
        # --- SNIFFING FILTER ---
        user_id, is_own_roll = identify_roll_owner(bot, message)
        
        # Track roll owner for kakera debt tracking
        if user_id:
            bot.kakera_tracker.track_roll(message.id, user_id)

        claiming_cfg = bot.config.get("claiming", {})
        sniffing_enabled = claiming_cfg.get("sniffing_enabled", True)
        blacklist = claiming_cfg.get("sniff_blacklist", [])

        should_interact = is_own_roll or (sniffing_enabled and str(user_id) not in [str(b) for b in blacklist])

        if should_interact:
            logger.info(f"BUTTON DETECTED! Clicking immediately... (Owner: {user_id}, Own: {is_own_roll})")
            try:
                await target_button.click()
                return 
            except Exception as e:
                logger.error(f"Failed to click button: {e}")
        else:
            logger.debug(f"Ignoring button roll from {user_id} (Sniffing disabled or blacklisted)")

    if not message.embeds:
        return

    embed = message.embeds[0]
    description = embed.description if embed.description else ""
    desc_lower = description.lower()
    
    # Check fields as well for "Animanga roulette"
    fields_text = " ".join([f.value for f in embed.fields]).lower() if embed.fields else ""
    full_text_lower = desc_lower + " " + fields_text

    # Identify if it's a Roll or an Info ($im) message
    is_roll = ROLL_INDICATOR_PATTERN.search(desc_lower) and embed.image
    is_info = "animanga roulette" in full_text_lower and not ROLL_INDICATOR_PATTERN.search(desc_lower)

    if is_roll or is_info:
        # Signal that we received a response for a roll (or $im check)
        bot.roll_response_event.set()

    if is_roll:
        character_name = "Unknown"
        if embed.author:
            character_name = embed.author.name
        elif embed.title:
            character_name = embed.title
            
        logger.info(f"ROLL DETECTED: {character_name}")

        # --- SNIFFING FILTER ---
        user_id, is_own_roll = identify_roll_owner(bot, message)
        
        # Track roll owner for kakera debt tracking
        if user_id:
            bot.kakera_tracker.track_roll(message.id, user_id)

        claiming_cfg = bot.config.get("claiming", {})
        sniffing_enabled = claiming_cfg.get("sniffing_enabled", True)
        blacklist = claiming_cfg.get("sniff_blacklist", [])
        
        should_interact = is_own_roll or (sniffing_enabled and str(user_id) not in [str(b) for b in blacklist])

        if not should_interact:
            logger.debug(f"Ignoring roll for {character_name} from {user_id} (Sniffing disabled or blacklisted)")
            return

        # 3. Wishlist Check (Immediate Reaction Fallback)
        if is_in_wishlist(bot, character_name):
            logger.info(f"WISHLIST MATCH: {character_name}. Attempting immediate reaction!")
            await perform_claim(bot, message)
            return

        # 4. Kakera Check via $im (Only for OUR rolls)
        if is_own_roll:
            # Use the full name provided by Mudae (preserving parentheses)
            clean_name = character_name.strip()
            logger.info(f"OWN ROLL: {character_name}. Sending $im '{clean_name}' to check kakera...")
            bot.pending_kakera_checks[clean_name.lower()] = message
            await human_delay((0.5, 0.8))
            await message.channel.send(f"$im {clean_name}")
        return

    if is_info:
        # 5. Process $im Response
        character_name = "Unknown"
        if embed.author:
            character_name = embed.author.name
        elif embed.title:
            character_name = embed.title
        
        # Keep the full name for matching
        clean_char_name = character_name.strip().lower()
        logger.info(f"INFO MESSAGE for '{character_name}' (normalized: '{clean_char_name}')")
        
        # Try to find the original roll message
        original_roll_message = None
        if clean_char_name in bot.pending_kakera_checks:
            original_roll_message = bot.pending_kakera_checks.pop(clean_char_name)
        else:
            # Fallback fuzzy match
            for key in list(bot.pending_kakera_checks.keys()):
                if key in clean_char_name or clean_char_name in key:
                    original_roll_message = bot.pending_kakera_checks.pop(key)
                    break

        if original_roll_message:
            kakera_value = 0
            match = KAKERA_PATTERN.search(full_text_lower)
            if match:
                kakera_value = int(match.group(1))
            
            # Save roll info for last-hour fallback
            bot.current_sequence_rolls.append({
                "name": character_name,
                "kakera": kakera_value,
                "message": original_roll_message
            })
            
            claiming_cfg = bot.config.get("claiming", {})
            min_kakera = claiming_cfg.get("min_kakera", 999999)

            from src.logic.roller import is_last_hour_of_interval
            is_last_hour = is_last_hour_of_interval(bot)

            logger.info(f"KAKERA EVALUATION: {character_name} = {kakera_value} kakera. (Threshold: {min_kakera})")

            # PATIENCE LOGIC: In last hour, we wait until the end of the sequence to pick the BEST one.
            # We only claim immediately if it's NOT the last hour.
            if not is_last_hour:
                if kakera_value >= min_kakera:
                    logger.info(f"CLAIMING: {character_name} ({kakera_value} >= {min_kakera})")
                    await perform_claim(bot, original_roll_message)
                else:
                    logger.info(f"SKIPPING: {character_name} ({kakera_value} < {min_kakera})")
            else:
                logger.info(f"LAST HOUR PATIENCE: Saving {character_name} ({kakera_value} kakera) for later evaluation.")


def is_in_wishlist(bot, name):
    claiming_cfg = bot.config.get("claiming", {})
    wishlist = [w.lower() for w in claiming_cfg.get("wishlist", [])]
    return name.lower() in wishlist

async def perform_claim(bot, message):
    await human_delay((0.7, 1.3)) # Increased delay to appear more human
    try:
        await message.add_reaction("❤️")
        logger.info("Claimed via reaction!")
    except Exception as e:
        logger.error(f"Reaction failed: {e}")
