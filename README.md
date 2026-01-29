# DevOps Agent

Telegram бот для управления серверами через SSH с помощью Claude AI.

## Возможности

- Выполнение команд на удалённых серверах через SSH
- Agentic Loop — агент сам решает какие команды выполнить
- Многоуровневая безопасность (permission levels, dangerous patterns)
- Поддержка нескольких серверов
- История сессий и инцидентов в SQLite
- Выбор модели Claude (Sonnet/Opus/Haiku)

## Архитектура

```
┌─────────────────┐     ┌───────────────┐     ┌─────────────────┐
│  Telegram User  │────►│  DevOpsBot    │────►│  DevOpsAgent    │
└─────────────────┘     │  (aiogram 3)  │     │  (agentic loop) │
                        └───────────────┘     └────────┬────────┘
                                                       │
                              ┌────────────────────────┼────────────────────┐
                              ▼                        ▼                    ▼
                        ┌───────────┐          ┌─────────────┐      ┌──────────────┐
                        │ToolRegistry│          │ SSH Manager │      │ State Manager│
                        │ ssh_execute│          │ (asyncssh)  │      │ (aiosqlite)  │
                        │ ssh_list   │          └─────────────┘      └──────────────┘
                        └───────────┘
```

## Установка

### 1. Клонировать репозиторий

```bash
git clone https://github.com/temrjan/devops-agent.git
cd devops-agent
```

### 2. Создать виртуальное окружение

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Или установить зависимости вручную:

```bash
pip install aiogram anthropic pydantic pydantic-settings aiosqlite structlog asyncssh
```

### 3. Настроить конфигурацию

Скопировать `.env.example` в `.env` и заполнить:

```bash
cp .env.example .env
```

```env
# Telegram Bot
TELEGRAM_BOT_TOKEN=your_bot_token
ALLOWED_USER_IDS=[your_telegram_id]

# Anthropic API
ANTHROPIC_API_KEY=your_anthropic_key

# Debug mode
DEBUG=false
```

### 4. Настроить SSH серверы

Отредактировать `config/ssh_permissions.json`:

```json
{
  "hosts": {
    "localhost": {
      "level": "admin",
      "description": "Local server"
    },
    "production": {
      "level": "operator",
      "description": "Production server"
    }
  },
  "default_host": "localhost"
}
```

SSH подключения используют стандартный `~/.ssh/config`.

### 5. Запустить

```bash
python -m src.main
```

Или через PM2:

```bash
pm2 start ecosystem.config.js
```

## Permission Levels

| Уровень | Разрешено |
|---------|-----------|
| readonly | cat, ls, df, ps, docker ps, systemctl status |
| operator | + systemctl restart, docker restart |
| admin | Почти всё (кроме опасных команд) |

## Команды бота

| Команда | Описание |
|---------|----------|
| /start | Начало работы |
| /health | Состояние сервера |
| /logs <service> | Логи сервиса |
| /servers | Список серверов |
| /model | Выбор модели Claude |
| /status | Статистика агента |
| /history | История инцидентов |

## Примеры использования

Просто напишите боту что нужно сделать:

- "покажи место на диске"
- "перезапусти nginx"
- "последние 50 строк логов api"
- "сколько памяти свободно на production"
- "docker ps на сервере staging"

## Стек технологий

- Python 3.11+
- aiogram 3.x — Telegram Bot API
- anthropic — Claude API
- asyncssh — SSH подключения
- aiosqlite — SQLite для состояния
- pydantic — валидация конфигурации
- structlog — структурированное логирование

## Безопасность

- Whitelist пользователей по Telegram ID
- Permission levels для каждого сервера
- Блокировка опасных команд (rm -rf /, fork bomb, etc.)
- Audit log всех действий

## Лицензия

MIT
