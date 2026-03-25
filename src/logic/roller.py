import logging
import asyncio
from datetime import datetime, timezone
from src.utils.humanizer import human_delay
from src.logic.timer_manager import check_timers

logger = logging.getLogger(__name__)

def get_current_interval_start(bot):
    """Calculates the start time of the current 3-hour Mudae interval in UTC."""
    cfg = bot.config.get("claiming", {})
    interval_hours = cfg.get("claim_reset_interval", 3)
    start_hour_utc = cfg.get("claim_reset_start", 0)
    
    now = datetime.now(timezone.utc)
    # Total hours since the start_hour_utc
    hours_since_start = (now.hour - start_hour_utc) % 24
    # Find how many full intervals have passed
    intervals_passed = hours_since_start // interval_hours
    # Current interval start hour
    current_interval_hour = (start_hour_utc + (intervals_passed * interval_hours)) % 24
    
    return now.replace(hour=current_interval_hour, minute=0, second=0, microsecond=0)

async def perform_rolls(bot):
    """Sends a sequence of roll commands with humanized delays, checking for intervals."""
    # 1. Check if we already claimed in this interval
    current_interval = get_current_interval_start(bot)
    if bot.last_claim_interval_start == current_interval:
        logger.info(f"Skipping rolls: Already claimed in this interval ({current_interval.strftime('%H:%M')} UTC).")
        return

    # 2. Check available rolls via $tu
    await check_timers(bot)
    # Wait a bit for Mudae to respond and the bot to parse it
    # We'll wait up to 5 seconds for available_rolls to be updated
    for _ in range(5):
        if bot.available_rolls > 0:
            break
        await asyncio.sleep(1)

    if bot.available_rolls <= 0:
        logger.info("No rolls available according to $tu (or timed out). Skipping.")
        return

    channel_id = bot.target_channel_id
    if not channel_id:
        logger.error("No target channel ID configured. Skipping rolls.")
        return

    channel = bot.get_channel(channel_id)
    if not channel:
        try:
            channel = await bot.fetch_channel(channel_id)
        except Exception as e:
            logger.error(f"Could not find channel {channel_id}: {e}")
            return

    roll_cmd = bot.config.get("roll_command", "$wa")
    num_rolls = bot.available_rolls
    
    # Delay at the very start of the hour
    start_delay_range = bot.config.get("timing", {}).get("start_delay_range", [1.0, 5.0])
    await human_delay(start_delay_range)

    roll_delay_range = bot.config.get("timing", {}).get("roll_delay_range", [0.5, 2.5])

    logger.info(f"Starting {num_rolls} rolls with command '{roll_cmd}'...")
    
    # Store this task so we can cancel it if we claim
    bot.current_rolling_task = asyncio.current_task()

    try:
        for i in range(num_rolls):
            logger.debug(f"Sending roll {i+1}/{num_rolls}")
            await channel.send(roll_cmd)
            # Update internal count
            bot.available_rolls -= 1
            
            # Don't delay after the last roll
            if i < num_rolls - 1:
                await human_delay(roll_delay_range)
    except asyncio.CancelledError:
        logger.info("Roll sequence CANCELLED (Claim successful!).")
    except Exception as e:
        logger.error(f"Error during roll sequence: {e}")
    finally:
        bot.available_rolls = 0 # Reset after sequence
        bot.current_rolling_task = None
        logger.info(f"Finished roll sequence for this hour.")
