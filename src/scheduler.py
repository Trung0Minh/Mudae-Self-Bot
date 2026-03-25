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
        logger.info("New hour detected! Triggering roll sequence...")
        
        # We'll import the roller logic here to avoid circular imports if needed
        from src.logic.roller import perform_rolls
        await perform_rolls(self.bot)

    def shutdown(self):
        """Stops the scheduler."""
        self.scheduler.shutdown()
