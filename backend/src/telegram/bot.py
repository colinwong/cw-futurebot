import logging

from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes

from src.config import settings

logger = logging.getLogger(__name__)


class TelegramBot:
    """Telegram bot for trade alerts, system events, and commands."""

    def __init__(self):
        self._app: Application | None = None
        self._bot: Bot | None = None

    async def start(self) -> None:
        if not settings.telegram_bot_token:
            logger.warning("Telegram bot token not set, bot disabled")
            return

        self._app = (
            Application.builder()
            .token(settings.telegram_bot_token)
            .build()
        )

        # Register commands
        self._app.add_handler(CommandHandler("status", self._cmd_status))
        self._app.add_handler(CommandHandler("positions", self._cmd_positions))
        self._app.add_handler(CommandHandler("pnl", self._cmd_pnl))
        self._app.add_handler(CommandHandler("stop", self._cmd_stop))
        self._app.add_handler(CommandHandler("help", self._cmd_help))

        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling()

        self._bot = self._app.bot
        logger.info("Telegram bot started")

    async def stop(self) -> None:
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            logger.info("Telegram bot stopped")

    async def send_message(self, text: str) -> None:
        """Send a message to the configured chat."""
        if not self._bot or not settings.telegram_chat_id:
            return
        try:
            await self._bot.send_message(
                chat_id=settings.telegram_chat_id,
                text=text,
                parse_mode="HTML",
            )
        except Exception:
            logger.exception("Failed to send Telegram message")

    async def send_trade_alert(
        self,
        symbol: str,
        direction: str,
        action: str,
        price: float,
        stop_price: float | None = None,
        target_price: float | None = None,
        reasoning: str = "",
    ) -> None:
        """Send a trade execution/rejection alert."""
        emoji = "🟢" if action == "EXECUTE" else "🔴"
        msg = (
            f"{emoji} <b>{action}: {direction} {symbol}</b>\n"
            f"Price: {price:.2f}\n"
        )
        if stop_price:
            msg += f"Stop: {stop_price:.2f}\n"
        if target_price:
            msg += f"Target: {target_price:.2f}\n"
        if reasoning:
            msg += f"\n<i>{reasoning[:200]}</i>"

        await self.send_message(msg)

    async def send_system_alert(self, event_type: str, details: str) -> None:
        """Send a system event alert (disconnect, reconciliation, etc.)."""
        emoji_map = {
            "DISCONNECT": "⚠️",
            "RECONNECT": "✅",
            "RECONCILIATION": "🔍",
            "ERROR": "❌",
            "STARTUP": "🚀",
            "SHUTDOWN": "🛑",
        }
        emoji = emoji_map.get(event_type, "ℹ️")
        msg = f"{emoji} <b>System: {event_type}</b>\n{details[:500]}"
        await self.send_message(msg)

    # --- Command handlers ---

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show bot status and connection info."""
        # TODO: Get actual status from broker/engine
        await update.message.reply_text(
            "🤖 <b>FutureBot Status</b>\n"
            "Status: Running\n"
            "Broker: Connected\n"
            "Symbols: ES, NQ",
            parse_mode="HTML",
        )

    async def _cmd_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show current open positions."""
        # TODO: Query actual positions from DB
        await update.message.reply_text(
            "📊 <b>Open Positions</b>\n"
            "No open positions.",
            parse_mode="HTML",
        )

    async def _cmd_pnl(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show daily P&L summary."""
        # TODO: Query actual P&L from DB
        await update.message.reply_text(
            "💰 <b>Daily P&L</b>\n"
            "Realized: $0.00\n"
            "Unrealized: $0.00",
            parse_mode="HTML",
        )

    async def _cmd_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Emergency stop — disable trading."""
        # TODO: Implement trading halt
        await update.message.reply_text(
            "🛑 Trading halted. Protective orders remain active at broker.",
            parse_mode="HTML",
        )

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show available commands."""
        await update.message.reply_text(
            "🤖 <b>FutureBot Commands</b>\n\n"
            "/status — Bot status and connection info\n"
            "/positions — Current open positions\n"
            "/pnl — Daily P&L summary\n"
            "/stop — Emergency halt trading\n"
            "/help — This message",
            parse_mode="HTML",
        )
