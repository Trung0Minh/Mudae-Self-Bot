import asyncio
import sys
import logging
from src.config_loader import load_config, setup_logging
from src.bot import MudaeBot

logger = logging.getLogger(__name__)

async def main():
    config = load_config()
    setup_logging(config)
    
    token = config.get("token")
    if not token:
        logger.error("No DISCORD_TOKEN found in environment variables. Check your .env file.")
        sys.exit(1)

    bot = MudaeBot(config)

    try:
        # discord.py-self's bot.run handles the event loop correctly for us
        await bot.start(token)
    except KeyboardInterrupt:
        await bot.close()
    except Exception as e:
        logger.critical(f"Bot stopped due to an error: {e}", exc_info=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
