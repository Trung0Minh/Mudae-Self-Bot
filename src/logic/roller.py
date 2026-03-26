import logging
import asyncio
from datetime import datetime, timezone, timedelta
from src.utils.humanizer import human_delay
from src.logic.timer_manager import check_timers

logger = logging.getLogger(__name__)

def get_current_interval_start(bot):
    """Calculates the start time of the current Mudae claim interval in UTC."""
    # Specific reset hours provided by the user
    RESETS = [1, 4, 7, 11, 13, 16, 19, 22]
    
    now = datetime.now(timezone.utc)
    current_hour = now.hour
    
    # Handle wrap-around: if current hour is before the first reset (1 AM UTC),
    # it belongs to the last reset of the previous day (22:00 UTC).
    if current_hour < RESETS[0]:
        prev_day = now - timedelta(days=1)
        return prev_day.replace(hour=RESETS[-1], minute=0, second=0, microsecond=0)
    
    # Find the latest reset hour that is less than or equal to the current hour
    interval_hour = RESETS[0]
    for r in RESETS:
        if r <= current_hour:
            interval_hour = r
        else:
            break
            
    return now.replace(hour=interval_hour, minute=0, second=0, microsecond=0)

async def perform_rolls(bot):
    """Sends a sequence of roll commands with humanized delays, checking for intervals."""
    # 1. Backup Check: Check if we already claimed in this interval (internal state)
    current_interval = get_current_interval_start(bot)
    if bot.last_claim_interval_start == current_interval:
        logger.info(f"Skipping rolls: Already claimed in this interval ({current_interval.strftime('%H:%M')} UTC).")
        return

    # 2. Source of Truth Check: Check $tu
    await check_timers(bot)
    # Wait up to 5 seconds for Mudae to respond and the bot to parse the status
    for _ in range(5):
        # We check both available_rolls and the claim_ready flag
        # (Even if rolls are 0, we want to see if claim is ready)
        await asyncio.sleep(1)
        # If we successfully parsed a response, we stop waiting
        # We'll know we parsed it if available_rolls was updated or claim_ready was set
        # Actually, let's just wait the full time to be safe or check a specific flag.
        pass

    if not bot.claim_ready:
        logger.info("CLAIM NOT READY according to $tu. Skipping rolls for this hour.")
        return

    if bot.available_rolls <= 0:
        logger.info("No rolls available according to $tu. Skipping.")
        return

    channel_id = bot.target_channel_id
    channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
    if not channel:
        logger.error(f"Could not find channel {channel_id}.")
        return

    roll_cmd = bot.config.get("roll_command", "$wa")
    num_rolls = bot.available_rolls
    
    # Delay at the very start of the hour
    start_delay_range = bot.config.get("timing", {}).get("start_delay_range", [1.0, 5.0])
    await human_delay(start_delay_range)

    roll_delay_range = bot.config.get("timing", {}).get("roll_delay_range", [1.5, 2.5])

    logger.info(f"Starting {num_rolls} rolls with command '{roll_cmd}'...")
    
    # Store this task so we can cancel it if we claim
    bot.current_rolling_task = asyncio.current_task()

    try:
        for i in range(num_rolls):
            logger.debug(f"Sending roll {i+1}/{num_rolls}")
            await channel.send(roll_cmd)
            bot.available_rolls -= 1
            
            if i < num_rolls - 1:
                await human_delay(roll_delay_range)
    except asyncio.CancelledError:
        logger.info("Roll sequence CANCELLED (Claim successful!).")
    except Exception as e:
        logger.error(f"Error during roll sequence: {e}")
    finally:
        bot.available_rolls = 0 
        bot.current_rolling_task = None
        logger.info(f"Finished roll sequence for this hour.")
