import logging
import asyncio
from datetime import datetime, timezone, timedelta
from src.utils.humanizer import human_delay
from src.logic.timer_manager import check_timers

logger = logging.getLogger(__name__)

def get_current_interval_start(bot):
    """Calculates the start time of the current Mudae claim interval in UTC."""
    RESETS = [1, 4, 7, 11, 13, 16, 19, 22]
    now = datetime.now(timezone.utc)
    current_hour = now.hour
    
    if current_hour < RESETS[0]:
        prev_day = now - timedelta(days=1)
        return prev_day.replace(hour=RESETS[-1], minute=0, second=0, microsecond=0)
    
    interval_hour = RESETS[0]
    for r in RESETS:
        if r <= current_hour:
            interval_hour = r
        else:
            break
    return now.replace(hour=interval_hour, minute=0, second=0, microsecond=0)

def is_last_hour_of_interval():
    """Checks if the current UTC hour is the last one before a claim reset."""
    RESETS = [1, 4, 7, 11, 13, 16, 19, 22]
    now = datetime.now(timezone.utc)
    current_hour = now.hour
    
    # Find the next reset
    next_reset = RESETS[0]
    for r in RESETS:
        if r > current_hour:
            next_reset = r
            break
    
    # If current_hour is 0 and RESETS[0] is 1, then 0 is the last hour
    if current_hour == 0 and next_reset == 1:
        return True
    
    return current_hour == (next_reset - 1)

async def perform_rolls(bot):
    """Unified roll sequence: $dk -> $daily -> (Rolls) -> $rolls -> (Extra Rolls)"""
    # 1. Check $tu first to refresh ALL states
    await check_timers(bot)
    await asyncio.sleep(6) # Wait for response

    # 2. Check if claim is even possible
    current_interval = get_current_interval_start(bot)
    if bot.last_claim_interval_start == current_interval:
        logger.info(f"Already claimed in this interval ({current_interval.strftime('%H:%M')} UTC).")
        if not bot.config.get("roll_without_claim", False):
            return

    if not bot.claim_ready:
        logger.info("Claim not ready according to $tu. Skipping.")
        return

    channel_id = bot.target_channel_id
    channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
    if not channel:
        return

    # Store this task early so claimer knows we are rolling
    bot.current_rolling_task = asyncio.current_task()
    bot.current_sequence_rolls = [] # Reset for this sequence
    
    is_last_hour = is_last_hour_of_interval()
    if is_last_hour:
        logger.info("LAST HOUR before reset! Enabling best-of-sequence fallback.")

    try:
        # 3. Handle DK and Daily
        used_daily = False
        if bot.dk_ready:
            logger.info("Sequence: Sending $dk")
            await channel.send("$dk")
            await human_delay((1.5, 3.0))

        if bot.daily_ready:
            logger.info("Sequence: Sending $daily")
            await channel.send("$daily")
            used_daily = True
            await human_delay((2.0, 4.0))

        # 4. Perform Initial Rolls
        roll_cmd = bot.config.get("roll_command", "$wa")
        num_rolls = bot.available_rolls
        
        if num_rolls > 0:
            logger.info(f"Sequence: Starting {num_rolls} initial rolls")
            for i in range(num_rolls):
                await channel.send(roll_cmd)
                bot.available_rolls -= 1
                if i < num_rolls - 1:
                    await human_delay((1.5, 2.5))
                else:
                    await asyncio.sleep(3.0) # Buffer for last $im

        # 5. Extra Rolls (if $daily was used)
        if used_daily:
            logger.info("Sequence: Daily was used, requesting extra rolls via $rolls")
            await channel.send("$rolls")
            await human_delay((3.0, 5.0))
            
            logger.info("Sequence: Starting 10 extra rolls from $daily")
            for i in range(10):
                await channel.send(roll_cmd)
                if i < 9:
                    await human_delay((1.5, 2.5))
                else:
                    await asyncio.sleep(4.0) # Longer buffer after final roll

        # 6. Final Last-Hour Check
        if is_last_hour and bot.last_claim_interval_start != current_interval:
            if bot.current_sequence_rolls:
                # Find the roll with the highest kakera value
                best_roll = max(bot.current_sequence_rolls, key=lambda x: x["kakera"])
                logger.info(f"LAST HOUR FALLBACK: Claiming best available character: {best_roll['name']} ({best_roll['kakera']} kakera)")
                from src.logic.claimer import perform_claim
                await perform_claim(bot, best_roll["message"])
                
                # --- DIVORCE FOR KAKERA ---
                # Wait for claim to process and Mudae to confirm "married" (about 6-8 seconds is safe)
                await asyncio.sleep(8.0)
                
                # Clean name for $divorce command (e.g. "Rem (Re:Zero)" -> "Rem")
                clean_name = best_roll["name"].split(" (")[0].split(" - ")[0].strip()
                logger.info(f"LAST HOUR FALLBACK: Divorcing {clean_name} to collect kakera...")
                
                await channel.send(f"$divorce {clean_name}")
                await asyncio.sleep(2.5) # Wait for Mudae's confirmation request
                await channel.send("y")
                logger.info(f"Divorce confirmation sent for {clean_name}.")
            else:
                logger.info("LAST HOUR FALLBACK: No rolls were captured in this sequence.")

    except asyncio.CancelledError:
        logger.info("Roll sequence cancelled (Claimed!).")
    except Exception as e:
        logger.error(f"Error during roll sequence: {e}")
    finally:
        bot.available_rolls = 0 
        bot.current_rolling_task = None
        bot.current_sequence_rolls = []
        logger.info("Unified roll sequence finished.")
