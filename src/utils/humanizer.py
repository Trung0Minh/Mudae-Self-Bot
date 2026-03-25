import random
import asyncio
import logging

logger = logging.getLogger(__name__)

async def human_delay(range_tuple=(0.5, 2.0)):
    """Async sleep for a random duration within the given range."""
    delay = random.uniform(range_tuple[0], range_tuple[1])
    # logger.debug(f"Sleeping for {delay:.2f}s...")
    await asyncio.sleep(delay)

def get_random_delay(range_tuple=(0.5, 2.0)):
    """Returns a random float between the given range."""
    return random.uniform(range_tuple[0], range_tuple[1])
