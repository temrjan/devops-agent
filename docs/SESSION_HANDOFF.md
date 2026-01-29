# DevOps Agent — ТЗ для продолжения

## Проект

**Путь:** `/home/temrjan/claude-agent/`

**Цель:** Telegram бот + Claude AI агент для управления сервером. Получает команды в Telegram, диагностирует и чинит проблемы, верифицирует результат.

## Выполнено

### Этап 0: Окружение ✅
- Python 3.14.2, venv, pip
- Зависимости: aiogram 3.24, anthropic 0.76, pydantic, pytest, ruff, mypy

### Этап 1: Конфигурация ✅
- `pyproject.toml`
- `src/config.py` — Pydantic Settings
- `.env.example`
- `config/allowlist.json` — разрешённые команды
- `tests/test_config.py` — 4 теста pass

## Осталось

| Этап | Описание | Файлы |
|------|----------|-------|
| 2 | Модуль безопасности | `src/security.py`, `tests/test_security.py` |
| 3 | DevOps инструменты | `src/tools.py`, `tests/test_tools.py` |
| 4 | Управление состоянием | `src/state.py`, `tests/test_state.py` |
| 5 | Agentic Loop | `src/agent.py`, `tests/test_agent.py` |
| 6 | Telegram Bot | `src/bot.py`, `tests/test_bot.py` |
| 7 | Интеграционные тесты | `tests/test_integration.py` |
| 8 | Развёртывание | systemd, запуск |

## Ключевые файлы

```
/home/temrjan/claude-agent/
├── CLAUDE.md                    # Память проекта, правила MCP
├── docs/
│   ├── IMPLEMENTATION_PLAN.md   # Полный план (~500 строк)
│   ├── SESSION_HANDOFF.md       # Этот файл
│   └── standards/               # Style guides (Python, Telegram, etc.)
├── src/
│   ├── config.py                # ✅ Готов
│   └── (остальное создать)
├── tests/
│   └── test_config.py           # ✅ 4 теста pass
├── config/
│   └── allowlist.json           # ✅ Разрешённые команды
├── venv/                        # ✅ Virtual environment
└── pyproject.toml               # ✅ Конфиг проекта
```

## Стандарты

**Обязательно читать:** `docs/standards/PYTHON_STYLE_GUIDE_V2.md`

Ключевое:
- Type hints везде
- Google docstrings
- pytest + AAA pattern
- ruff format/check, mypy

## Активация окружения

```bash
cd /home/temrjan/claude-agent
source venv/bin/activate
```

## Запуск тестов

```bash
TELEGRAM_BOT_TOKEN=test ANTHROPIC_API_KEY=test pytest -v
```

## MCP серверы

При большой работе с кодом использовать `sequential-thinking` MCP.

## Следующий шаг

**Этап 2:** Создать `src/security.py` с:
- `SecurityGuard` класс
- Проверка пользователей по allowlist
- Проверка команд по allowlist
- Аудит логирование
- Защита от опасных паттернов

Детали в `docs/IMPLEMENTATION_PLAN.md` раздел "Этап 2".
