import logging
import asyncio
import discord
from src.utils.humanizer import human_delay

logger = logging.getLogger(__name__)

async def settle_all_debts(bot):
    """
    Weekly task to automatically pay back everyone in the ledger.
    """
    tracker = bot.kakera_tracker
    target_channel = bot.get_channel(bot.target_channel_id)
    
    if not target_channel:
        logger.error("Could not find target channel to perform settlement.")
        return

    # Snapshot of users with debt > 0
    to_pay = {uid: balance for uid, balance in tracker.ledger.items() if balance > 0}
    
    if not to_pay:
        logger.info("Auto-Settlement: No debts found. Skipping.")
        return

    logger.info(f"Auto-Settlement: Found {len(to_pay)} users to pay.")
    
    if tracker.pinned_message:
        await tracker.pinned_message.channel.send("📅 **Weekly Auto-Settlement Starting!**")

    for user_id, amount in to_pay.items():
        try:
            if user_id == bot.user.id:
                continue

            logger.info(f"Auto-Settlement: Paying back {user_id}: {amount} kakera")
            
            # Step 1: Send the gift command
            await target_channel.send(f"$givek <@{user_id}> {amount}")
            
            # Step 2: Wait for confirmation prompt
            def check_prompt(m):
                return (m.author.id == 432610292342587392 and 
                        m.channel.id == bot.target_channel_id and 
                        "do you really want to give" in m.content.lower())

            try:
                await bot.wait_for('message', check=check_prompt, timeout=10.0)
                await human_delay((1.5, 3.0))
                await target_channel.send("y")
                
                # Step 3: Wait for result (Success or Error)
                def check_result(m):
                    return (m.author.id == 432610292342587392 and 
                            m.channel.id == bot.target_channel_id and 
                            ("just gifted" in m.content.lower() or "not enough kakera" in m.content.lower()))

                result_msg = await bot.wait_for('message', check=check_result, timeout=10.0)
                
                if "not enough kakera" in result_msg.content.lower():
                    logger.error("Auto-Settlement: FAILED (Not enough kakera). Stopping entire process.")
                    if tracker.pinned_message:
                        await tracker.pinned_message.channel.send("⚠️ **Auto-Settlement STOPPED:** Not enough kakera to continue.")
                    return # STOP everything

                logger.info(f"Auto-Settlement: Successfully paid {user_id}.")
                
            except asyncio.TimeoutError:
                logger.warning(f"Auto-Settlement: Mudae timed out for user {user_id}. Skipping.")
            
            # Delay between users
            await human_delay((5.0, 8.0))

        except Exception as e:
            logger.error(f"Auto-Settlement Error for {user_id}: {e}")

    if tracker.pinned_message:
        await tracker.pinned_message.channel.send("✅ **Weekly Auto-Settlement Finished!** Ledger updated.")
