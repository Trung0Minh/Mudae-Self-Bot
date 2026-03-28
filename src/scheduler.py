from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import logging
from datetime import datetime, timedelta
import pytz

logger = logging.getLogger(__name__)

class MudaeScheduler:
    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config
        timezone_str = self.config.get("timing", {}).get("timezone", "UTC")
        self.timezone = pytz.timezone(timezone_str)
        self.scheduler = AsyncIOScheduler(timezone=self.timezone)

    def start(self):
        """Starts the scheduler."""
        # Trigger at the start of every hour (HH:00:00)
        self.scheduler.add_job(
            self.on_hour_trigger,
            CronTrigger(minute=0, second=0),
            id="hourly_roll"
        )
        self.scheduler.start()
        logger.info(f"Scheduler started with timezone: {self.timezone}")
        
        # Log when the next run is
        next_run = self.scheduler.get_job("hourly_roll").next_run_time
        logger.info(f"Next scheduled roll at: {next_run}")

    async def on_hour_trigger(self):
        """Callback for when a new hour starts."""
        from src.logic.roller import is_last_hour_of_interval, perform_rolls
        
        is_last_hour = is_last_hour_of_interval(self.bot)
        if is_last_hour:
            # DELAYED STRIKE: If it's the last hour, wait until minute 58
            logger.info("LAST HOUR detected. Delaying roll sequence until minute 58 to maximize snipe uptime...")
            
            # Calculate sleep time until MM:58:00
            now = datetime.now(self.timezone)
            target_time = now.replace(minute=58, second=0, microsecond=0)
            
            # If for some reason we are already past minute 58, don't sleep
            if target_time > now:
                sleep_seconds = (target_time - now).total_seconds()
                logger.info(f"Sleeping for {sleep_seconds:.1f} seconds until minute 58.")
                await asyncio.sleep(sleep_seconds)
            else:
                logger.info("Already past minute 58, starting rolls immediately.")

        logger.info("Triggering roll sequence...")
        await perform_rolls(self.bot)

    def shutdown(self):
        """Stops the scheduler."""
        self.scheduler.shutdown()
