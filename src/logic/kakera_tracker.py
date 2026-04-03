import logging
import re
import discord
from typing import Dict, Union

logger = logging.getLogger(__name__)

# Regex for kakera claim confirmation: Skip any emoji/prefix at the start, then match "Username +142 ($k)"
# Using .*? to lazily skip potential emojis/spaces at the start
CLAIM_CONFIRM_PATTERN = re.compile(r".*?([^\s\n]+)\s+\+(\d+)\s+\(\$k\)", re.IGNORECASE)

# Regex for kakera payment confirmation: "@user just gifted 500 💎 to @target"
PAYMENT_CONFIRM_PATTERN = re.compile(r"<@!?\d+>\s+just\s+gifted\s+(\d+)\s+.*?\s+to\s+<@!?(\d+)>", re.IGNORECASE)

# Regex to detect roll commands (e.g., $wa, $ha, $ma, $mg, /wa, etc.)
ROLL_COMMAND_PATTERN = re.compile(r"^[$/]([whma][ag]|wa|ha|ma|mg|w|h|m)", re.IGNORECASE)

LEDGER_HEADER = "--- KAKERA DEBT TRACKER ---"
LEDGER_FOOTER = "---------------------------"

class KakeraTracker:
    def __init__(self, bot):
        self.bot = bot
        self.channel_id = int(bot.config.get("tracker_channel_id", 0))
        # user_id (int) or username (str) -> amount (int)
        self.ledger: Dict[Union[int, str], int] = {} 
        self.pinned_message = None

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

    async def find_roller_username(self, confirmation_msg):
        """
        Trace back through history to find the person who triggered the roll.
        1. Find the nearest preceding Mudae message with a button.
        2. Find the nearest roll command ($wa, etc.) before that.
        """
        try:
            # Look back at last 20 messages
            history = await confirmation_msg.channel.history(limit=20, before=confirmation_msg).flatten()
            
            button_msg = None
            # Step 1: Find the roll message (Mudae message with a button)
            for msg in history:
                if msg.author.id == 432610292342587392 and msg.components:
                    # Check if any component is a button (kakera or character)
                    has_button = False
                    for row in msg.components:
                        for comp in row.children:
                            if isinstance(comp, discord.Button):
                                has_button = True
                                break
                    if has_button:
                        button_msg = msg
                        break
            
            if not button_msg:
                return None

            # Step 2: Find the nearest roll command BEFORE that button message
            # We look in the history starting from the button message
            found_button = False
            for msg in history:
                if msg.id == button_msg.id:
                    found_button = True
                    continue
                
                if found_button:
                    # Ignore other Mudae messages or bot messages
                    if msg.author.id == self.bot.user.id or msg.author.id == 432610292342587392:
                        continue
                    
                    # Check if the message content looks like a roll command
                    if ROLL_COMMAND_PATTERN.match(msg.content.strip()):
                        return msg.author.name
            
            return None
        except Exception as e:
            logger.error(f"Error tracing back roller: {e}")
            return None

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

        # Check for Claim Confirmation: "Username +142 ($k)"
        claim_match = CLAIM_CONFIRM_PATTERN.match(message.content)
        if claim_match:
            claimer_name = claim_match.group(1).lower()
            amount = int(claim_match.group(2))
            
            # Verify if it's OUR bot claiming
            bot_names = [self.bot.user.name.lower()]
            if self.bot.user.display_name:
                bot_names.append(self.bot.user.display_name.lower())
            
            is_bot_claim = claimer_name in bot_names or str(self.bot.user.id) in claimer_name
            
            if is_bot_claim:
                # Trace back to find the real roller
                roller_name = await self.find_roller_username(message)
                
                if roller_name:
                    # Check if roller is the bot itself (ignore own rolls)
                    is_own = roller_name.lower() in bot_names
                    
                    if not is_own:
                        self.ledger[roller_name] = self.ledger.get(roller_name, 0) + amount
                        logger.info(f"TRACE-BACK SUCCESS: Added {amount} kakera debt to {roller_name}. New balance: {self.ledger[roller_name]}")
                        await self._save_ledger()
                    else:
                        logger.debug("Skipping claim: Roller was the bot itself.")
                else:
                    logger.warning(f"TRACE-BACK FAILED to identify roller for claim of {amount} kakera.")
            return

        # Check for Payment Confirmation
        payment_match = PAYMENT_CONFIRM_PATTERN.search(message.content)
        if payment_match:
            amount = int(payment_match.group(1))
            paid_user_id = int(payment_match.group(2))
            
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
                except Exception:
                    pass

            if target_key:
                self.ledger[target_key] -= amount
                logger.info(f"PAYMENT SUCCESS: Deducted {amount} kakera debt from {target_key}. New balance: {self.ledger[target_key]}")
                await self._save_ledger()
            return
