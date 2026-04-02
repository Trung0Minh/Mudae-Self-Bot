import logging
import re
import discord
from typing import Dict, Union

logger = logging.getLogger(__name__)

# Regex for kakera claim confirmation: "Username +142 ($k)"
CLAIM_CONFIRM_PATTERN = re.compile(r"^([^ \n]+)\s+\+(\d+)\s+\(\$k\)", re.IGNORECASE)

# Regex for kakera payment confirmation: "500 kakera have been given to @User"
PAYMENT_CONFIRM_PATTERN = re.compile(r"(\d+)\s+kakera\s+have\s+been\s+given\s+to\s+<@!?(\d+)>", re.IGNORECASE)

LEDGER_HEADER = "--- KAKERA DEBT TRACKER ---"
LEDGER_FOOTER = "---------------------------"

class KakeraTracker:
    def __init__(self, bot):
        self.bot = bot
        self.channel_id = int(bot.config.get("tracker_channel_id", 0))
        # user_id (int) or username (str) -> amount (int)
        self.ledger: Dict[Union[int, str], int] = {} 
        self.pinned_message = None
        # Maps message_id of a roll to the user_id/username who rolled it
        self.recent_roll_owners: Dict[int, Union[int, str]] = {}
        # Maximum number of recent rolls to track to prevent memory leak
        self.MAX_TRACKED_ROLLS = 100

    async def initialize(self):
        """Load the ledger from the pinned message in the tracker channel."""
        if not self.channel_id:
            logger.warning("No tracker_channel_id found in config. Tracker disabled.")
            return

        channel = self.bot.get_channel(self.channel_id)
        if not channel:
            try:
                channel = await self.bot.fetch_channel(self.channel_id)
            except Exception as e:
                logger.error(f"Could not find tracker channel {self.channel_id}: {e}")
                return

        try:
            pins = await channel.pins()
            for msg in pins:
                if LEDGER_HEADER in msg.content:
                    self.pinned_message = msg
                    self._parse_ledger(msg.content)
                    logger.info(f"Loaded kakera ledger with {len(self.ledger)} users.")
                    return

            # If no pinned message found, create one
            logger.info("No pinned ledger found. Creating a new one...")
            self.pinned_message = await channel.send(self._format_ledger())
            await self.pinned_message.pin()
        except Exception as e:
            logger.error(f"Error during tracker initialization: {e}")

    def _parse_ledger(self, content: str):
        """Parse the ledger string from the pinned message."""
        self.ledger = {}
        lines = content.split("\n")
        for line in lines:
            if "|" in line and "UserID:" in line:
                try:
                    # Format: UserID: 123456789 | Balance: 1450
                    parts = line.split("|")
                    key_part = parts[0].split("UserID:")[1].strip()
                    balance = int(parts[1].split("Balance:")[1].strip())
                    
                    try:
                        key = int(key_part)
                    except ValueError:
                        key = key_part
                        
                    self.ledger[key] = balance
                except (IndexError, ValueError):
                    continue

    def _format_ledger(self) -> str:
        """Format the ledger dictionary into a string for the pinned message."""
        lines = [LEDGER_HEADER]
        # Sort by balance descending
        sorted_ledger = sorted(self.ledger.items(), key=lambda x: x[1], reverse=True)
        for key, balance in sorted_ledger:
            if balance != 0:
                # If it's an ID, try to make it look nicer or just keep it
                label = f"UserID: {key}"
                lines.append(f"{label} | Balance: {balance}")
        
        if len(lines) == 1:
            lines.append("(No active debts)")
            
        lines.append(LEDGER_FOOTER)
        return "\n".join(lines)

    async def _save_ledger(self):
        """Update the pinned message with the current ledger."""
        if self.pinned_message:
            try:
                await self.pinned_message.edit(content=self._format_ledger())
            except Exception as e:
                logger.error(f"Failed to update pinned ledger: {e}")

    def track_roll(self, message_id: int, owner: Union[int, str]):
        """Record who rolled a character."""
        # Normalize owner
        try:
            owner = int(owner)
        except (ValueError, TypeError):
            owner = str(owner).lower()
            
        self.recent_roll_owners[message_id] = owner
        
        # Cleanup old rolls
        if len(self.recent_roll_owners) > self.MAX_TRACKED_ROLLS:
            # Pop the oldest key (first one in dict)
            oldest_key = next(iter(self.recent_roll_owners))
            self.recent_roll_owners.pop(oldest_key)

    async def handle_message(self, message):
        """Handle messages for claims, payments, and commands."""
        # 1. Check for commands in the tracker channel or target channel
        if message.channel.id == self.channel_id or message.channel.id == self.bot.target_channel_id:
            if message.content.lower().startswith("$kstats"):
                await message.channel.send(f"**Current Kakera Debt:**\n{self._format_ledger()}")
                return

        # 2. Check for Mudae messages (Claims/Payments)
        # Mudae ID: 432610292342587392
        if message.author.id != 432610292342587392:
            return

        # DEBUG: Log all Mudae messages for analysis
        logger.debug(f"Mudae message received: '{message.content}'")

        # Check for Claim Confirmation: "Username +142 ($k)"
        claim_match = CLAIM_CONFIRM_PATTERN.match(message.content)
        if claim_match:
            claimer_name = claim_match.group(1).lower()
            amount = int(claim_match.group(2))
            
            # Verify if it's OUR bot claiming
            bot_names = [self.bot.user.name.lower()]
            if self.bot.user.display_name:
                bot_names.append(self.bot.user.display_name.lower())
            
            logger.debug(f"Claim detected: {claimer_name} got {amount}. Bot names: {bot_names}")

            # Check if name matches (handling potential mentions like <@ID>)
            is_bot_claim = claimer_name in bot_names or str(self.bot.user.id) in claimer_name
            
            if is_bot_claim:
                # We claimed kakera! Find whose roll it was.
                roller_id = None
                
                # Priority 1: Check if it's a reply to a known roll
                if message.reference and message.reference.message_id:
                    ref_id = message.reference.message_id
                    roller_id = self.recent_roll_owners.get(ref_id)
                    logger.debug(f"Found roller via message reference ({ref_id}): {roller_id}")
                
                # Priority 2: Look at the most recent tracked roll
                if not roller_id and self.recent_roll_owners:
                    # Get the last added roll owner (the most recent one)
                    recent_rolls = list(self.recent_roll_owners.items())
                    last_msg_id, last_roller = recent_rolls[-1]
                    roller_id = last_roller
                    logger.debug(f"Found roller via recent history (Last roll ID {last_msg_id}): {roller_id}")

                if roller_id:
                    if roller_id != self.bot.user.id:
                        self.ledger[roller_id] = self.ledger.get(roller_id, 0) + amount
                        logger.info(f"SUCCESS: Added {amount} kakera debt to {roller_id}. New balance: {self.ledger[roller_id]}")
                        await self._save_ledger()
                    else:
                        logger.debug("Skipping claim: Roller was the bot itself.")
                else:
                    logger.warning(f"FAILED to identify roller for claim of {amount} kakera. (History size: {len(self.recent_roll_owners)})")
            return

        # Check for Payment Confirmation
        payment_match = PAYMENT_CONFIRM_PATTERN.search(message.content)
        if payment_match:
            amount = int(payment_match.group(1))
            paid_user_id = int(payment_match.group(2))
            logger.debug(f"Payment detected: {amount} given to {paid_user_id}")
            
            target_key = None
            if paid_user_id in self.ledger:
                target_key = paid_user_id
            else:
                try:
                    user = self.bot.get_user(paid_user_id) or await self.bot.fetch_user(paid_user_id)
                    if user:
                        name_lower = user.name.lower()
                        if name_lower in self.ledger:
                            target_key = name_lower
                        elif user.display_name.lower() in self.ledger:
                            target_key = user.display_name.lower()
                except Exception as e:
                    logger.debug(f"Could not resolve user {paid_user_id} for payment: {e}")

            if target_key:
                self.ledger[target_key] -= amount
                logger.info(f"SUCCESS: Deducted {amount} kakera debt from {target_key}. New balance: {self.ledger[target_key]}")
                await self._save_ledger()
            else:
                logger.warning(f"FAILED to find user {paid_user_id} in debt list for payment of {amount} kakera.")
            return
