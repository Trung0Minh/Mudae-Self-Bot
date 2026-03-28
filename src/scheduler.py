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
            # DELAYED STRIKE: Schedule a separate job for minute 58
            now = datetime.now(self.timezone)
            target_time = now.replace(minute=58, second=0, microsecond=0)
            
            if target_time > now:
                logger.info(f"LAST HOUR detected. Scheduling delayed strike at {target_time.strftime('%H:%M:%S')}...")
                self.scheduler.add_job(
                    self.perform_delayed_rolls,
                    'date',
                    run_date=target_time,
                    id="delayed_strike"
                )
                return # Exit this trigger; the delayed job will handle the rolls
            else:
                logger.info("LAST HOUR detected but already past minute 58. Starting rolls immediately.")

        logger.info("Triggering roll sequence...")
        await perform_rolls(self.bot)

    async def perform_delayed_rolls(self):
        """Helper to run rolls after the delay."""
        logger.info("DELAYED STRIKE WAKING UP: Starting roll sequence now!")
        from src.logic.roller import perform_rolls
        await perform_rolls(self.bot)

    def shutdown(self):
        """Stops the scheduler."""
        self.scheduler.shutdown()
