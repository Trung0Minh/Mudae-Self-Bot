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

async def perform_rolls(bot):
    """Unified roll sequence: $dk -> $daily -> (Rolls) -> $rolls -> (Extra Rolls)"""
    # 1. Check $tu first to refresh ALL states
    await check_timers(bot)
    await asyncio.sleep(6) # Increased wait for response

    # 2. Check if claim is even possible
    current_interval = get_current_interval_start(bot)
    if bot.last_claim_interval_start == current_interval:
        logger.info(f"Already claimed in this interval ({current_interval.strftime('%H:%M')} UTC).")
        # Even if we claimed, we might want to do $dk/$daily? 
        # But usually we only roll if we can claim.
        if not bot.config.get("roll_without_claim", False):
            return

    if not bot.claim_ready:
        logger.info("Claim not ready according to $tu. Skipping.")
        return

    channel_id = bot.target_channel_id
    channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
    if not channel:
        return

    # 3. Handle DK and Daily (The start of the sequence)
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

    # 4. Perform Initial Rolls (from the hour reset)
    roll_cmd = bot.config.get("roll_command", "$wa")
    num_rolls = bot.available_rolls
    
    if num_rolls > 0:
        logger.info(f"Sequence: Starting {num_rolls} initial rolls")
        bot.current_rolling_task = asyncio.current_task()
        try:
            for i in range(num_rolls):
                await channel.send(roll_cmd)
                bot.available_rolls -= 1
                if i < num_rolls - 1:
                    await human_delay((1.5, 2.5))
        except asyncio.CancelledError:
            logger.info("Roll sequence cancelled (Claimed!).")
            return

    # 5. Extra Rolls (if $daily was used)
    if used_daily:
        logger.info("Sequence: Daily was used, requesting extra rolls via $rolls")
        await channel.send("$rolls")
        # Delay for Mudae to confirm $rolls
        await human_delay((3.0, 5.0))
        
        logger.info("Sequence: Starting 10 extra rolls from $daily")
        try:
            for i in range(10):
                await channel.send(roll_cmd)
                if i < 9:
                    await human_delay((1.5, 2.5))
        except asyncio.CancelledError:
            logger.info("Extra roll sequence cancelled (Claimed!).")
            return

    logger.info("Unified roll sequence finished.")
