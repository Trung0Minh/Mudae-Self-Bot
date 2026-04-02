import discord
import asyncio
from discord.ext import commands
import logging
from src.scheduler import MudaeScheduler
from src.logic.claimer import handle_mudae_message
from src.logic.timer_manager import handle_timer_response
from src.logic.kakera_tracker import KakeraTracker

logger = logging.getLogger(__name__)

class MudaeBot(commands.Bot):
    def __init__(self, config, *args, **kwargs):
        # Specify the browser to mimic. "chrome" or "firefox" are good options.
        # This helps avoid 503 "overflow" errors.
        super().__init__(command_prefix="!", self_bot=True, browser="chrome", *args, **kwargs)
        self.config = config
        self.target_channel_id = int(config.get("target_channel_id", 0))
        self.tracker_channel_id = int(config.get("tracker_channel_id", 0))
        self.scheduler = None
        # Stores the START time of the interval where we last claimed (UTC)
        self.last_claim_interval_start = None
        # To track if we are currently in the middle of a roll sequence
        self.current_rolling_task = None
        # Number of rolls available to use
        self.available_rolls = 0
        # Tracks pending $im checks: {character_name_lower: original_roll_message}
        self.pending_kakera_checks = {}
        # Tracks all rolls in the current sequence for last-hour fallback
        self.current_sequence_rolls = []
        # Tracks if Mudae says our claim is ready
        self.claim_ready = False
        # Flags for daily commands
        self.dk_ready = False
        self.daily_ready = False
        self.rolls_stock = 0
        # Event to signal when a roll response is received from Mudae
        self.roll_response_event = asyncio.Event()
        # To prevent cancellation during the divorce sequence
        self.is_divorcing = False
        
        # Kakera Tracker
        self.kakera_tracker = KakeraTracker(self)

    async def on_ready(self):
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        logger.info(f"Targeting channel: {self.target_channel_id}")
        logger.info(f"Tracker channel: {self.tracker_channel_id}")
        
        # Initialize tracker
        await self.kakera_tracker.initialize()

        # Initialize and start scheduler
        if not self.scheduler:
            self.scheduler = MudaeScheduler(self)
            self.scheduler.start()
            logger.info("Hourly scheduler initialized and started.")

    async def on_message(self, message):
        # Ignore our own messages (except for commands we might want to trigger?)
        # For a self-bot, we might want to trigger our own commands like $kstats if typed manually
        if message.author.id == self.user.id:
            # Allow our own commands in the tracker channel OR target channel
            if message.channel.id == self.tracker_channel_id or message.channel.id == self.target_channel_id:
                await self.kakera_tracker.handle_message(message)
            return

        # 1. Process Kakera Tracker logic (handles all channels, filtered internally)
        await self.kakera_tracker.handle_message(message)

        # 2. Restrict other logic to the target channel
        if message.channel.id != self.target_channel_id:
            return

        # 3. Process timer responses (e.g., $tu output)
        if await handle_timer_response(self, message):
            return

        # 4. Process message for claims
        await handle_mudae_message(self, message)
        
        # Don't process commands to save on detection risk
        # await self.process_commands(message)

    async def on_error(self, event_method, *args, **kwargs):
        logger.error(f"Error in {event_method}:", exc_info=True)

    async def close(self):
        """Cleanup on shutdown."""
        if self.scheduler:
            self.scheduler.shutdown()
        await super().close()
