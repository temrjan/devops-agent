"""Telegram bot for DevOps Agent.

Provides the main bot class with middleware for authentication,
rate limiting, and message handling.
"""

import asyncio
import logging
import signal
import time
from collections import defaultdict

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from src.agent import DevOpsAgent
from src.config import settings
from src.security import SecurityGuard
from src.ssh_manager import SSHManager
from src.state import StateManager
from src.tools import ToolRegistry

logger = logging.getLogger(__name__)

# Available Claude models
MODELS = {
    "sonnet": ("claude-sonnet-4-20250514", "Sonnet 4"),
    "opus": ("claude-opus-4-20250514", "Opus 4"),
    "haiku": ("claude-3-5-haiku-20241022", "Haiku 3.5"),
}


class RateLimiter:
    """Simple in-memory rate limiter.

    Tracks message timestamps per user and enforces rate limits.

    Args:
        max_requests: Maximum requests allowed in the time window.
        window_seconds: Time window in seconds.
    """

    def __init__(self, max_requests: int = 10, window_seconds: int = 60) -> None:
        """Initialize rate limiter.

        Args:
            max_requests: Max requests per window.
            window_seconds: Window duration in seconds.
        """
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._requests: dict[int, list[float]] = defaultdict(list)

    def is_limited(self, user_id: int) -> bool:
        """Check if user is rate limited.

        Args:
            user_id: User ID to check.

        Returns:
            True if user has exceeded rate limit.
        """
        now = time.time()
        cutoff = now - self._window_seconds

        # Clean old requests
        self._requests[user_id] = [ts for ts in self._requests[user_id] if ts > cutoff]

        return len(self._requests[user_id]) >= self._max_requests

    def record(self, user_id: int) -> None:
        """Record a request for user.

        Args:
            user_id: User ID making the request.
        """
        self._requests[user_id].append(time.time())

    def reset(self, user_id: int) -> None:
        """Reset rate limit for user.

        Args:
            user_id: User ID to reset.
        """
        self._requests[user_id] = []


class DevOpsBot:
    """Telegram bot for DevOps operations.

    Integrates with DevOpsAgent to handle user requests,
    provides command handlers and message processing.

    Args:
        security_guard: Guard for user authorization.
        state_manager: Manager for session persistence.
        tool_registry: Registry of available tools.
        agent: DevOpsAgent for processing queries.
        bot: Optional aiogram Bot instance (for testing).
    """

    def __init__(
        self,
        security_guard: SecurityGuard,
        state_manager: StateManager,
        tool_registry: ToolRegistry,
        agent: DevOpsAgent,
        bot: Bot | None = None,
    ) -> None:
        """Initialize DevOpsBot.

        Args:
            security_guard: Security guard for authorization.
            state_manager: State manager for persistence.
            tool_registry: Tool registry for direct tool access.
            agent: DevOps agent for query processing.
            bot: Optional Bot instance for dependency injection.
        """
        self._security = security_guard
        self._state = state_manager
        self._tools = tool_registry
        self._agent = agent

        self._bot = bot or Bot(
            token=settings.telegram_bot_token.get_secret_value(),
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        self._dp = Dispatcher()
        self._router = Router()
        self._rate_limiter = RateLimiter(max_requests=10, window_seconds=60)

        self._setup_handlers()
        self._running = False

    def _setup_handlers(self) -> None:
        """Set up message handlers."""
        from aiogram.filters import Command, CommandStart

        @self._router.message(CommandStart())
        async def cmd_start(message: Message) -> None:
            await self._handle_start(message)

        @self._router.message(Command("help"))
        async def cmd_help(message: Message) -> None:
            await self._handle_help(message)

        @self._router.message(Command("health"))
        async def cmd_health(message: Message) -> None:
            await self._handle_health(message)

        @self._router.message(Command("logs"))
        async def cmd_logs(message: Message) -> None:
            await self._handle_logs(message)

        @self._router.message(Command("status"))
        async def cmd_status(message: Message) -> None:
            await self._handle_status(message)

        @self._router.message(Command("history"))
        async def cmd_history(message: Message) -> None:
            await self._handle_history(message)

        @self._router.message(Command("servers"))
        async def cmd_servers(message: Message) -> None:
            await self._handle_servers(message)

        @self._router.message(Command("model"))
        async def cmd_model(message: Message) -> None:
            await self._handle_model(message)

        @self._router.callback_query(F.data.startswith("model:"))
        async def callback_model(callback: CallbackQuery) -> None:
            await self._handle_model_callback(callback)

        @self._router.message()
        async def handle_message(message: Message) -> None:
            await self._handle_message(message)

        self._dp.include_router(self._router)

    async def _check_auth(self, message: Message) -> bool:
        """Check if user is authorized.

        Args:
            message: Incoming message.

        Returns:
            True if user is authorized.
        """
        user_id = message.from_user.id if message.from_user else 0

        if not self._security.is_user_allowed(user_id):
            logger.warning(f"Unauthorized access attempt from user {user_id}")
            self._security.audit_log(
                user_id, "bot_access", "Unauthorized", allowed=False
            )
            return False

        return True

    async def _check_rate_limit(self, message: Message) -> bool:
        """Check if user is rate limited.

        Args:
            message: Incoming message.

        Returns:
            True if user is NOT rate limited (can proceed).
        """
        user_id = message.from_user.id if message.from_user else 0

        if self._rate_limiter.is_limited(user_id):
            await message.answer("Слишком много запросов. Подождите минуту.")
            logger.warning(f"Rate limit exceeded for user {user_id}")
            return False

        self._rate_limiter.record(user_id)
        return True

    async def _handle_start(self, message: Message) -> None:
        """Handle /start command.

        Args:
            message: Incoming message.
        """
        if not await self._check_auth(message):
            return

        text = """
<b>DevOps Agent (SSH)</b>

Я помогу управлять серверами через SSH. Доступные команды:

/health — состояние системы
/logs &lt;service&gt; — логи сервиса
/servers — список серверов
/model — выбор модели Claude
/status — статус агента
/history — последние инциденты
/help — справка

Или просто напишите, что нужно сделать.
Примеры:
• проверь место на диске на biotact
• перезапусти nginx на staging
• покажи docker ps на prod-1
"""
        await message.answer(text.strip())

    async def _handle_help(self, message: Message) -> None:
        """Handle /help command.

        Args:
            message: Incoming message.
        """
        if not await self._check_auth(message):
            return

        text = """
<b>Справка — SSH DevOps Agent</b>

<b>Команды:</b>
/start — начало работы
/servers — список доступных серверов
/model — выбор модели (Sonnet/Opus/Haiku)
/health — CPU, память, диск
/logs nginx — логи сервиса
/status — статус агента
/history — последние инциденты

<b>Примеры запросов:</b>
• проверь статус nginx на biotact
• перезапусти docker контейнер app на staging
• покажи docker logs app на prod-1
• сколько места на диске на dev
• выполни df -h на backup

<b>Permission levels:</b>
• readonly — только чтение
• operator — чтение + restart сервисов
• admin — полный доступ

Агент выполняет команды через SSH на удалённых серверах.
"""
        await message.answer(text.strip())

    async def _handle_health(self, message: Message) -> None:
        """Handle /health command.

        Args:
            message: Incoming message.
        """
        if not await self._check_auth(message):
            return
        if not await self._check_rate_limit(message):
            return

        user_id = message.from_user.id if message.from_user else 0

        await message.answer("Проверяю состояние системы...")

        # Get user's selected model from database
        model_key = await self._state.get_user_model(user_id)
        model_id = MODELS.get(model_key, MODELS["sonnet"])[0]

        # Use agent to check health via SSH
        result = await self._agent.run(
            user_id=user_id,
            query="Покажи состояние системы: CPU, память, диск (df -h, free -m, uptime)",
            model=model_id,
        )

        if result.success:
            await message.answer(result.response or "Проверка завершена.")
        else:
            await message.answer(f"Ошибка: {result.error}")

    async def _handle_logs(self, message: Message) -> None:
        """Handle /logs command.

        Args:
            message: Incoming message.
        """
        if not await self._check_auth(message):
            return
        if not await self._check_rate_limit(message):
            return

        user_id = message.from_user.id if message.from_user else 0

        # Parse service name from command
        text = message.text or ""
        parts = text.split(maxsplit=1)

        if len(parts) < 2:
            await message.answer("Укажите сервис: <code>/logs nginx</code>")
            return

        service = parts[1].strip()
        await message.answer(f"Читаю логи {service}...")

        # Get user's selected model from database
        model_key = await self._state.get_user_model(user_id)
        model_id = MODELS.get(model_key, MODELS["sonnet"])[0]

        # Use agent to read logs via SSH
        result = await self._agent.run(
            user_id=user_id,
            query=f"Покажи последние 50 строк логов сервиса {service} (journalctl -u {service} -n 50)",
            model=model_id,
        )

        if result.success:
            await message.answer(result.response or "Логи получены.")
        else:
            await message.answer(f"Ошибка: {result.error}")

    async def _handle_status(self, message: Message) -> None:
        """Handle /status command.

        Args:
            message: Incoming message.
        """
        if not await self._check_auth(message):
            return

        user_id = message.from_user.id if message.from_user else 0

        # Get session info
        session = await self._state.get_active_session(user_id)
        session_info = "активна" if session else "нет активной сессии"

        # Get incident stats
        stats = await self._state.get_incident_stats(user_id=user_id)

        text = f"""
<b>Статус агента</b>

Сессия: {session_info}
Всего инцидентов: {stats["total_incidents"]}
Успешных: {stats["successful_incidents"]}
Успешность: {stats["success_rate"]:.0%}
Среднее время: {stats["average_duration_seconds"]:.1f} сек
"""
        await message.answer(text.strip())

    async def _handle_history(self, message: Message) -> None:
        """Handle /history command.

        Args:
            message: Incoming message.
        """
        if not await self._check_auth(message):
            return

        user_id = message.from_user.id if message.from_user else 0

        incidents = await self._state.get_recent_incidents(user_id=user_id, limit=5)

        if not incidents:
            await message.answer("История инцидентов пуста.")
            return

        lines = ["<b>Последние инциденты:</b>\n"]
        for inc in incidents:
            status = "✅" if inc.success else "❌"
            time_str = inc.timestamp.strftime("%d.%m %H:%M")
            query_short = inc.query[:50] + "..." if len(inc.query) > 50 else inc.query
            lines.append(f"{status} [{time_str}] {query_short}")

        await message.answer("\n".join(lines))

    async def _handle_servers(self, message: Message) -> None:
        """Handle /servers command.

        Args:
            message: Incoming message.
        """
        if not await self._check_auth(message):
            return

        user_id = message.from_user.id if message.from_user else 0

        # Use ssh_list_hosts tool
        result = await self._tools.execute("ssh_list_hosts", user_id=user_id)

        if result.success:
            await message.answer(f"<pre>{result.output}</pre>")
        else:
            await message.answer(f"Ошибка: {result.error}")

    async def _handle_model(self, message: Message) -> None:
        """Handle /model command.

        Args:
            message: Incoming message.
        """
        if not await self._check_auth(message):
            return

        user_id = message.from_user.id if message.from_user else 0
        current_key = await self._state.get_user_model(user_id)
        current_name = MODELS.get(current_key, MODELS["sonnet"])[1]

        # Build inline keyboard
        buttons = []
        for key, (model_id, name) in MODELS.items():
            marker = " ✓" if key == current_key else ""
            buttons.append(
                InlineKeyboardButton(text=f"{name}{marker}", callback_data=f"model:{key}")
            )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[buttons])

        await message.answer(
            f"<b>Выбор модели Claude</b>\n\nТекущая: {current_name}",
            reply_markup=keyboard,
        )

    async def _handle_model_callback(self, callback: CallbackQuery) -> None:
        """Handle model selection callback.

        Args:
            callback: Callback query from inline button.
        """
        if not callback.message or not callback.from_user:
            return

        user_id = callback.from_user.id

        if not self._security.is_user_allowed(user_id):
            await callback.answer("Доступ запрещён", show_alert=True)
            return

        # Extract model key from callback data
        model_key = callback.data.split(":")[1] if callback.data else "sonnet"

        if model_key not in MODELS:
            await callback.answer("Неизвестная модель", show_alert=True)
            return

        # Save user preference to database
        await self._state.set_user_model(user_id, model_key)
        model_name = MODELS[model_key][1]

        # Update keyboard with new selection
        buttons = []
        for key, (model_id, name) in MODELS.items():
            marker = " ✓" if key == model_key else ""
            buttons.append(
                InlineKeyboardButton(text=f"{name}{marker}", callback_data=f"model:{key}")
            )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[buttons])

        await callback.message.edit_text(
            f"<b>Выбор модели Claude</b>\n\nТекущая: {model_name}",
            reply_markup=keyboard,
        )
        await callback.answer(f"Модель: {model_name}")

    async def _handle_message(self, message: Message) -> None:
        """Handle regular text messages.

        Args:
            message: Incoming message.
        """
        if not await self._check_auth(message):
            return
        if not await self._check_rate_limit(message):
            return

        user_id = message.from_user.id if message.from_user else 0
        text = message.text or ""

        if not text.strip():
            return

        logger.info(f"Processing message from user {user_id}: {text[:50]}...")

        # Send typing indicator
        await message.answer("Обрабатываю запрос...")

        # Get user's selected model from database
        model_key = await self._state.get_user_model(user_id)
        model_id = MODELS.get(model_key, MODELS["sonnet"])[0]

        # Run agent
        result = await self._agent.run(user_id=user_id, query=text, model=model_id)

        if result.success:
            response = result.response or "Задача выполнена."

            # Add tools info if any were used
            if result.tools_used:
                tools_str = ", ".join(result.tools_used)
                response += f"\n\n<i>Использованы: {tools_str}</i>"

            # Split long messages
            for chunk in self._split_message(response):
                await message.answer(chunk)
        else:
            error_msg = result.error or "Неизвестная ошибка"
            await message.answer(f"Ошибка: {error_msg}")

    def _split_message(self, text: str, max_length: int = 4000) -> list[str]:
        """Split long message into chunks.

        Args:
            text: Text to split.
            max_length: Maximum chunk length.

        Returns:
            List of text chunks.
        """
        if len(text) <= max_length:
            return [text]

        chunks = []
        while text:
            if len(text) <= max_length:
                chunks.append(text)
                break

            # Find split point
            split_at = text.rfind("\n", 0, max_length)
            if split_at == -1:
                split_at = max_length

            chunks.append(text[:split_at])
            text = text[split_at:].lstrip()

        return chunks

    async def start(self) -> None:
        """Start the bot polling."""
        logger.info("Starting DevOps Bot...")

        # Initialize state manager
        await self._state.initialize()

        self._running = True

        # Set up signal handlers
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))

        try:
            await self._dp.start_polling(self._bot)
        finally:
            self._running = False

    async def stop(self) -> None:
        """Stop the bot gracefully."""
        logger.info("Stopping DevOps Bot...")
        self._running = False
        await self._dp.stop_polling()
        await self._bot.session.close()
        await self._state.close()

    @property
    def is_running(self) -> bool:
        """Check if bot is running."""
        return self._running

    @property
    def rate_limiter(self) -> RateLimiter:
        """Get rate limiter instance."""
        return self._rate_limiter


async def create_bot() -> DevOpsBot:
    """Create and configure DevOpsBot instance.

    Returns:
        Configured DevOpsBot.
    """
    security = SecurityGuard()
    state = StateManager()

    # Initialize SSH Manager
    ssh_manager = SSHManager(
        permissions_path=settings.effective_ssh_permissions_path,
        security=security,
        ssh_config_path=settings.ssh_config_path,
        known_hosts_path=settings.ssh_known_hosts_path,
    )
    await ssh_manager.initialize()

    # Create tools with SSH manager
    tools = ToolRegistry(
        ssh_manager=ssh_manager,
        security_guard=security,
    )

    # Create agent
    agent = DevOpsAgent(
        tool_registry=tools,
        state_manager=state,
        security_guard=security,
        ssh_manager=ssh_manager,
    )

    return DevOpsBot(
        security_guard=security,
        state_manager=state,
        tool_registry=tools,
        agent=agent,
    )
