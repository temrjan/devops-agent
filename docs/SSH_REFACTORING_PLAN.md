# SSH Refactoring Plan — DevOps Agent

> Версия: 2.0
> Дата: 2026-01-23
> Цель: Переход с локального выполнения команд на SSH-only архитектуру

---

## 1. Обзор изменений

### 1.1 Текущее состояние
- Агент выполняет команды **локально** через `asyncio.create_subprocess_shell()`
- 10 tools: run_command, check_service, restart_service, read_logs, docker_ps, docker_logs, docker_restart, system_health, check_port, verify_fix
- Все команды выполняются на машине, где запущен бот

### 1.2 Целевое состояние
- Агент выполняет команды **удалённо** через SSH
- 6 серверов с разными уровнями доступа
- 2 tools: `ssh_execute`, `ssh_list_hosts`
- Использование стандартного `~/.ssh/config`

### 1.3 Преимущества
- Управление серверами из любого места через Telegram
- Централизованный контроль над 6 серверами
- Использование существующей SSH инфраструктуры
- Упрощение кодовой базы (меньше tools)

---

## 2. Архитектура

### 2.1 Общая схема

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        ЛОКАЛЬНАЯ МАШИНА                                  │
│                                                                          │
│  ┌──────────────┐     ┌─────────────────────────────────────────────┐  │
│  │   Telegram   │     │              DevOps Agent                    │  │
│  │   Bot API    │◄───►│                                              │  │
│  └──────────────┘     │  ┌─────────┐  ┌──────────┐  ┌────────────┐  │  │
│                       │  │ Message │  │ Agentic  │  │    SSH     │  │  │
│                       │  │ Handler │─►│  Loop    │─►│  Manager   │  │  │
│                       │  └─────────┘  └──────────┘  └────────────┘  │  │
│                       └──────────────────────────────────────────────┘  │
│                                              │                           │
│                           ┌──────────────────┼──────────────────┐       │
│                           │                  │                  │       │
│                           ▼                  ▼                  ▼       │
│                    ┌───────────┐      ┌───────────┐      ┌───────────┐ │
│                    │ ~/.ssh/   │      │ ~/.ssh/   │      │ ~/.ssh/   │ │
│                    │ config    │      │ id_rsa    │      │known_hosts│ │
│                    └───────────┘      └───────────┘      └───────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
                                       │
                    SSH Connections    │
          ┌────────────────────────────┼────────────────────────────┐
          │                            │                            │
          ▼                            ▼                            ▼
┌─────────────────┐          ┌─────────────────┐          ┌─────────────────┐
│    biotact      │          │     prod-1      │          │     prod-2      │
│  95.111.224.251 │          │    10.0.0.1     │          │    10.0.0.2     │
│   port: 2222    │          │   port: 22      │          │   port: 22      │
│  level: admin   │          │ level: readonly │          │ level: operator │
└─────────────────┘          └─────────────────┘          └─────────────────┘
          │                            │                            │
          ▼                            ▼                            ▼
┌─────────────────┐          ┌─────────────────┐          ┌─────────────────┐
│    staging      │          │       dev       │          │     backup      │
│   10.0.1.1      │          │   10.0.2.1      │          │   10.0.3.1      │
│   port: 22      │          │   port: 22      │          │   port: 22      │
│  level: admin   │          │  level: admin   │          │ level: readonly │
└─────────────────┘          └─────────────────┘          └─────────────────┘
```

### 2.2 Модель соединений

```
┌─────────────────────────────────────────────────────────────────┐
│                    Connect-Execute-Disconnect                    │
│                                                                  │
│   Request                                                        │
│      │                                                           │
│      ▼                                                           │
│   ┌──────────────────┐                                          │
│   │   SSH Connect    │ ◄── Читает ~/.ssh/config                 │
│   │   (asyncssh)     │     Проверяет known_hosts                │
│   └────────┬─────────┘                                          │
│            │                                                     │
│            ▼                                                     │
│   ┌──────────────────┐                                          │
│   │  Execute Command │ ◄── timeout: 60s                         │
│   │   conn.run()     │     truncate output                      │
│   └────────┬─────────┘                                          │
│            │                                                     │
│            ▼                                                     │
│   ┌──────────────────┐                                          │
│   │   Disconnect     │ ◄── Автоматически через async with      │
│   └────────┬─────────┘                                          │
│            │                                                     │
│            ▼                                                     │
│        Response                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Почему не Connection Pool:**
- Редкие запросы (10-50 в день)
- SSH соединения "умирают" по таймауту
- Сложность keepalive/reconnect не оправдана
- Connect overhead ~0.5-2s — приемлемо

---

## 3. Конфигурация

### 3.1 Использование ~/.ssh/config

**Не дублируем конфигурацию!** Используем стандартный SSH config:

```ssh-config
# ~/.ssh/config (уже существует)

Host biotact
    HostName 95.111.224.251
    Port 2222
    User root
    IdentityFile ~/.ssh/id_rsa

Host prod-1
    HostName 10.0.0.1
    User deploy
    IdentityFile ~/.ssh/prod_key

Host prod-2
    HostName 10.0.0.2
    User deploy
    IdentityFile ~/.ssh/prod_key

Host staging
    HostName 10.0.1.1
    User root
    IdentityFile ~/.ssh/id_rsa

Host dev
    HostName 10.0.2.1
    User root
    IdentityFile ~/.ssh/id_rsa

Host backup
    HostName 10.0.3.1
    User backup
    IdentityFile ~/.ssh/backup_key
```

### 3.2 config/ssh_permissions.json

**Только права доступа и описания** (не IP/порты/ключи):

```json
{
  "hosts": {
    "biotact": {
      "level": "admin",
      "description": "BioTact MiniApp — основной сервер"
    },
    "prod-1": {
      "level": "readonly",
      "description": "Production 1 — только мониторинг"
    },
    "prod-2": {
      "level": "operator",
      "description": "Production 2 — мониторинг + restart"
    },
    "staging": {
      "level": "admin",
      "description": "Staging — тестовый сервер"
    },
    "dev": {
      "level": "admin",
      "description": "Development — разработка"
    },
    "backup": {
      "level": "readonly",
      "description": "Backup — только чтение"
    }
  },
  "default_host": "biotact",
  "connection_timeout": 10,
  "command_timeout": 60,
  "max_output_lines": 150,
  "max_output_bytes": 65536
}
```

### 3.3 Permission Levels

| Level | Описание | Разрешённые действия |
|-------|----------|---------------------|
| **readonly** | Только чтение | `cat`, `ls`, `df`, `free`, `ps`, `docker ps`, `systemctl status`, `journalctl`, `tail`, `head`, `grep` |
| **operator** | Чтение + управление сервисами | readonly + `systemctl restart/start/stop`, `docker restart`, `docker compose up/down/restart` |
| **admin** | Полный доступ | Всё, кроме dangerous patterns |

### 3.4 Обновление .env

```bash
# .env
TELEGRAM_BOT_TOKEN=...
ANTHROPIC_API_KEY=...
ALLOWED_USER_IDS=8503214095

# SSH Settings
SSH_CONFIG_PATH=~/.ssh/config
SSH_KNOWN_HOSTS_PATH=~/.ssh/known_hosts
SSH_DEFAULT_HOST=biotact
```

---

## 4. Безопасность

### 4.1 Трёхслойная валидация

```
┌─────────────────────────────────────────────────────────────────┐
│                      SECURITY LAYERS                             │
│                                                                  │
│   Layer 1: User Authorization                                    │
│   ├── is_user_allowed(user_id)?                                 │
│   └── Проверка ALLOWED_USER_IDS                                 │
│                                                                  │
│   Layer 2: Host Authorization                                    │
│   ├── is_host_allowed(host_alias)?                              │
│   └── Проверка ssh_permissions.json                             │
│                                                                  │
│   Layer 3: Command Validation                                    │
│   ├── check_dangerous_patterns(command)?                        │
│   ├── check_permission_level(host, command)?                    │
│   └── Audit logging                                              │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 Dangerous Patterns (блокируются ВСЕГДА)

```python
DANGEROUS_PATTERNS = [
    # Деструктивные
    r"rm\s+-rf\s+/",              # rm -rf /
    r"rm\s+-rf\s+\*",             # rm -rf *
    r"rm\s+-rf\s+~",              # rm -rf ~
    r"mkfs\.",                     # форматирование
    r"dd\s+if=",                   # raw disk
    r">\s*/dev/sd",               # запись на диск

    # Права доступа
    r"chmod\s+-R\s+777",          # небезопасные права
    r"chown\s+-R\s+root",         # смена владельца на root

    # Code injection
    r"\|\s*sh\b",                  # pipe to sh
    r"\|\s*bash\b",               # pipe to bash
    r"curl.*\|\s*bash",           # curl | bash
    r"wget.*\|\s*sh",             # wget | sh
    r"\$\(",                       # $(command) substitution
    r"`[^`]+`",                    # `command` substitution

    # Privilege escalation
    r"sudo\s+su\b",               # sudo su
    r"\bpasswd\b",                # смена пароля
    r"visudo",                    # редактирование sudoers

    # System destruction
    r">\s*/etc/",                 # перезапись /etc/
    r":\s*\(\s*\)\s*\{",          # fork bomb
    r"shutdown",                  # выключение
    r"reboot",                    # перезагрузка
    r"init\s+0",                  # halt

    # Interactive commands (зависнут)
    r"\bvim?\b",                  # vi/vim
    r"\bnano\b",                  # nano
    r"\bless\b",                  # less
    r"\bmore\b",                  # more
    r"\bmysql\s*$",               # mysql shell
    r"\bpsql\s*$",                # psql shell
    r"\bmongo\s*$",               # mongo shell
]
```

### 4.3 Per-Level Command Allowlists

```python
READONLY_COMMANDS = [
    # System info
    r"^cat\s+",
    r"^ls\s+",
    r"^df\s+",
    r"^free\s+",
    r"^uptime$",
    r"^top\s+-bn1",
    r"^ps\s+",
    r"^netstat\s+",
    r"^ss\s+",
    r"^du\s+",
    r"^head\s+",
    r"^tail\s+",
    r"^grep\s+",
    r"^find\s+",
    r"^wc\s+",

    # Service status (read-only)
    r"^systemctl\s+status\s+",
    r"^systemctl\s+is-active\s+",
    r"^journalctl\s+",

    # Docker status
    r"^docker\s+ps",
    r"^docker\s+logs\s+",
    r"^docker\s+inspect\s+",
    r"^docker\s+images",
    r"^docker\s+compose\s+ps",
    r"^docker\s+compose\s+logs",

    # Network
    r"^curl\s+",
    r"^ping\s+",
    r"^dig\s+",
    r"^nslookup\s+",
    r"^traceroute\s+",
]

OPERATOR_COMMANDS = READONLY_COMMANDS + [
    # Service management
    r"^systemctl\s+(restart|start|stop)\s+",
    r"^systemctl\s+reload\s+",

    # Docker management
    r"^docker\s+restart\s+",
    r"^docker\s+start\s+",
    r"^docker\s+stop\s+",
    r"^docker\s+compose\s+(up|down|restart)",
]

ADMIN_COMMANDS = None  # Все кроме dangerous patterns
```

### 4.4 Audit Logging

```json
{
  "timestamp": "2026-01-23T15:30:45.123456+00:00",
  "user_id": 8503214095,
  "action": "ssh_execute",
  "host": "biotact",
  "command": "systemctl restart nginx",
  "allowed": true,
  "permission_level": "admin",
  "exit_code": 0,
  "duration_ms": 1234
}
```

---

## 5. Tools

### 5.1 ssh_execute

```python
{
    "name": "ssh_execute",
    "description": "Execute a command on remote server via SSH",
    "parameters": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Command to execute"
            },
            "host": {
                "type": "string",
                "description": "Server alias from ssh_permissions.json (default: biotact)",
                "default": "biotact"
            },
            "timeout": {
                "type": "integer",
                "description": "Command timeout in seconds (default: 60)",
                "default": 60
            }
        },
        "required": ["command"]
    }
}
```

**Возвращает:**
```python
@dataclass
class SSHResult:
    success: bool
    output: str          # stdout (truncated if needed)
    error: str           # stderr
    exit_code: int
    host: str
    truncated: bool = False
    truncated_info: str | None = None  # "Показано 150 из 5000 строк"
```

### 5.2 ssh_list_hosts

```python
{
    "name": "ssh_list_hosts",
    "description": "List available SSH hosts and their permission levels",
    "parameters": {
        "type": "object",
        "properties": {}
    }
}
```

**Возвращает:**
```
Доступные серверы:

• biotact (admin) — BioTact MiniApp — основной сервер
• prod-1 (readonly) — Production 1 — только мониторинг
• prod-2 (operator) — Production 2 — мониторинг + restart
• staging (admin) — Staging — тестовый сервер
• dev (admin) — Development — разработка
• backup (readonly) — Backup — только чтение

По умолчанию: biotact
```

---

## 6. Обработка ошибок

### 6.1 SSH-специфичные ошибки

```python
ERROR_MESSAGES = {
    "connection_refused": "Сервер {host} отклонил соединение. Проверьте что SSH работает.",
    "timeout": "Сервер {host} не отвечает. Проверьте сеть и firewall.",
    "auth_failed": "Ошибка аутентификации на {host}. Проверьте SSH ключ.",
    "host_key_changed": "Host key {host} изменился! Возможна MITM атака или переустановка сервера.",
    "host_key_not_found": "Host key {host} не найден в known_hosts. Добавьте вручную.",
    "permission_denied": "Команда запрещена на {host} (уровень: {level}).",
    "command_timeout": "Команда на {host} превысила таймаут {timeout}с.",
    "unknown_host": "Сервер '{host}' не найден в конфигурации.",
}
```

### 6.2 Retry логика

```python
# Retry ТОЛЬКО для transient errors
RETRY_EXCEPTIONS = [
    asyncssh.DisconnectError,  # Connection dropped
    asyncio.TimeoutError,       # Network timeout
    OSError,                    # Network unreachable
]

# НЕ retry для:
# - asyncssh.PermissionDenied (auth failed)
# - asyncssh.HostKeyNotVerifiable (security)
# - CommandBlockedError (security)

MAX_RETRIES = 2
RETRY_DELAY = 1.0  # seconds
```

---

## 7. Output Truncation

### 7.1 Лимиты

```python
MAX_OUTPUT_LINES = 150      # Строк
MAX_OUTPUT_BYTES = 65536    # 64KB
```

### 7.2 Логика

```python
def truncate_output(output: str) -> tuple[str, bool, str | None]:
    """
    Returns: (truncated_output, was_truncated, info_message)
    """
    lines = output.split('\n')

    # Проверка по строкам
    if len(lines) > MAX_OUTPUT_LINES:
        truncated = '\n'.join(lines[:MAX_OUTPUT_LINES])
        info = f"Показано {MAX_OUTPUT_LINES} из {len(lines)} строк"
        return truncated, True, info

    # Проверка по байтам
    if len(output.encode()) > MAX_OUTPUT_BYTES:
        # Обрезаем с учётом UTF-8
        truncated = output[:MAX_OUTPUT_BYTES].rsplit('\n', 1)[0]
        info = f"Вывод обрезан до {MAX_OUTPUT_BYTES // 1024}KB"
        return truncated, True, info

    return output, False, None
```

---

## 8. System Prompt для Claude

```python
SSH_SYSTEM_PROMPT = """Ты DevOps агент с доступом к {num_hosts} серверам через SSH.

## Доступные серверы:
{hosts_list}

## Правила работы:

### 1. Выбор сервера
- По умолчанию используй: {default_host}
- Если пользователь указал сервер — используй его
- Если неясно какой сервер — спроси

### 2. Выполнение команд
ВАЖНО: Каждая команда выполняется в ОТДЕЛЬНОЙ сессии!
- Плохо: ssh_execute("cd /opt/app"), потом ssh_execute("docker compose ps")
- Хорошо: ssh_execute("cd /opt/app && docker compose ps")

### 3. Последовательность действий
1. GATHER — собери информацию (status, logs, df, ps)
2. ANALYZE — определи проблему
3. ACT — выполни исправление
4. VERIFY — проверь результат

### 4. Безопасность
- Проверяй permission level сервера
- На readonly серверах — только чтение
- На operator — чтение + restart сервисов
- На admin — почти всё (кроме опасных команд)

### 5. Интерактивные команды
НЕ используй команды, требующие ввода:
- vim, nano, less, more (используй cat, head, tail)
- mysql, psql без параметров (используй -e "query")
- apt upgrade без -y

## Контекст предыдущих инцидентов:
{incidents_context}
"""
```

---

## 9. План реализации

### Этап 1: Подготовка (15 мин)
- [ ] 1.1 Добавить `asyncssh>=2.14` в зависимости
- [ ] 1.2 Создать `config/ssh_permissions.json`
- [ ] 1.3 Проверить `~/.ssh/config` для 6 серверов
- [ ] 1.4 Проверить SSH подключение к каждому серверу

### Этап 2: SSHManager (45 мин)
- [ ] 2.1 Создать `src/ssh_manager.py`
- [ ] 2.2 Реализовать `SSHConfig` (чтение ~/.ssh/config)
- [ ] 2.3 Реализовать `SSHPermissions` (чтение ssh_permissions.json)
- [ ] 2.4 Реализовать `SSHManager.execute()`
- [ ] 2.5 Реализовать обработку ошибок
- [ ] 2.6 Реализовать truncation

### Этап 3: Security обновление (30 мин)
- [ ] 3.1 Добавить host validation в `SecurityGuard`
- [ ] 3.2 Добавить per-level command validation
- [ ] 3.3 Добавить новые dangerous patterns
- [ ] 3.4 Обновить audit logging

### Этап 4: Tools рефакторинг (30 мин)
- [ ] 4.1 Удалить старые локальные tools
- [ ] 4.2 Создать `SSHExecuteTool`
- [ ] 4.3 Создать `SSHListHostsTool`
- [ ] 4.4 Обновить `ToolRegistry`

### Этап 5: Agent обновление (20 мин)
- [ ] 5.1 Обновить system prompt
- [ ] 5.2 Интегрировать SSHManager
- [ ] 5.3 Обновить tools schema для Claude

### Этап 6: Config обновление (15 мин)
- [ ] 6.1 Добавить SSH settings в `Settings`
- [ ] 6.2 Обновить `.env.example`
- [ ] 6.3 Обновить документацию

### Этап 7: Тесты (1 час)
- [ ] 7.1 Написать unit тесты для SSHManager (mock asyncssh)
- [ ] 7.2 Написать тесты security per-level
- [ ] 7.3 Написать тесты для SSH tools
- [ ] 7.4 Обновить существующие тесты
- [ ] 7.5 Добавить integration тесты (опционально, требуют реальный сервер)

### Этап 8: Финализация (15 мин)
- [ ] 8.1 Запустить все тесты
- [ ] 8.2 Проверить работу с реальным сервером
- [ ] 8.3 Обновить IMPLEMENTATION_PLAN.md

---

## 10. Структура файлов после рефакторинга

```
src/
├── __init__.py
├── main.py                 # Entry point (без изменений)
├── config.py               # + SSHSettings
├── bot.py                  # Без изменений
├── agent.py                # + SSH system prompt, SSHManager
├── ssh_manager.py          # NEW: SSHManager
├── tools.py                # Рефакторинг: только SSH tools
├── security.py             # + host validation, per-level
└── state.py                # Без изменений

config/
├── allowlist.json          # Удалить или оставить для reference
└── ssh_permissions.json    # NEW: права серверов

tests/
├── test_ssh_manager.py     # NEW
├── test_tools.py           # Обновить
├── test_security.py        # Обновить
└── ...
```

---

## 11. Риски и митигации

| Риск | Митигация |
|------|-----------|
| SSH ключ недоступен | Проверка при старте, понятная ошибка |
| Сервер недоступен | Таймаут + retry + понятная ошибка |
| Host key изменился | Блокировка + предупреждение (MITM) |
| Команда зависла | Таймаут 60с + kill |
| Огромный вывод | Truncation 150 строк / 64KB |
| Компрометация бота | Audit log + per-host permissions |

---

## 12. Примеры использования

### Пример 1: Простая команда
```
User: Проверь место на диске на biotact

Agent думает:
  → ssh_execute(host="biotact", command="df -h")

Agent: На biotact:
  Filesystem      Size  Used Avail Use%
  /dev/sda1       100G   45G   55G  45%
  /dev/sdb1       500G  120G  380G  24%
```

### Пример 2: Работа с несколькими серверами
```
User: Проверь статус nginx на всех prod серверах

Agent думает:
  → ssh_execute(host="prod-1", command="systemctl status nginx")
  → ssh_execute(host="prod-2", command="systemctl status nginx")

Agent: Статус nginx:
  • prod-1: active (running), uptime 5 days
  • prod-2: active (running), uptime 12 days
```

### Пример 3: Отказ из-за permission level
```
User: Перезапусти nginx на prod-1

Agent думает:
  → ssh_execute(host="prod-1", command="systemctl restart nginx")

Agent: Не могу перезапустить nginx на prod-1.
  Сервер prod-1 имеет уровень доступа "readonly" — только чтение.

  Если нужно перезапустить, используй prod-2 (operator) или попроси админа.
```

### Пример 4: Работа в директории
```
User: Посмотри логи docker compose в /opt/myapp на dev

Agent думает:
  → ssh_execute(host="dev", command="cd /opt/myapp && docker compose logs --tail=50")

Agent: Последние 50 строк логов:
  [app]  2026-01-23 15:30:00 INFO: Server started
  [db]   2026-01-23 15:30:01 INFO: Database ready
  ...
```

---

*Документ создан: 2026-01-23*
*Автор: Claude Agent*
