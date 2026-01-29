# План реализации аналитики BioTact MiniApp

**Дата:** 2026-01-23
**Статус:** Готов к реализации
**Оценка времени:** 30-40 минут

---

## 1. Текущее состояние

### 1.1 Инфраструктура
- **Сервер:** biotact-miniapp (95.111.224.251:2222)
- **БД:** PostgreSQL `biotact_db`
- **Бот:** `/var/www/biotact/packages/bot`
- **API:** `/var/www/biotact/packages/api`

### 1.2 Текущие метрики
- Пользователей: 48
- Заказов: 24
- Активность: ~2-7 новых пользователей/день

### 1.3 Существующая аналитика
- Endpoint: `GET /analytics/dashboard`
- Метрики: выручка, заказы, топ продукты, статусы
- Файл: `/var/www/biotact/packages/api/src/analytics/service.py`

### 1.4 Проблема
- Нет отслеживания активности пользователей
- `updated_at` обновляется только при изменении профиля
- Невозможно узнать кто реально пользуется ботом

---

## 2. План изменений

### 2.1 Миграция базы данных

**Файл:** Новая миграция Alembic или прямой SQL

```sql
-- Добавить поле last_seen_at
ALTER TABLE users ADD COLUMN last_seen_at TIMESTAMPTZ;

-- Заполнить существующие записи
UPDATE users SET last_seen_at = COALESCE(updated_at, created_at);

-- Индекс для быстрых запросов
CREATE INDEX idx_users_last_seen ON users(last_seen_at);
```

### 2.2 Обновление модели User

**Файл:** `/var/www/biotact/packages/bot/bot/models/user.py`

```python
# Добавить после updated_at:
last_seen_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True),
    nullable=True,
)
```

**Файл:** `/var/www/biotact/packages/api/src/users/models.py`

```python
# Аналогично добавить last_seen_at
last_seen_at = Column(DateTime(timezone=True), nullable=True)
```

### 2.3 Middleware для отслеживания активности

**Новый файл:** `/var/www/biotact/packages/bot/bot/middlewares/activity.py`

```python
"""Activity tracking middleware."""

from datetime import datetime, UTC
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Update
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models.user import User


class ActivityMiddleware(BaseMiddleware):
    """Track user activity by updating last_seen_at."""

    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any],
    ) -> Any:
        # Get user from event
        user = None
        if event.message:
            user = event.message.from_user
        elif event.callback_query:
            user = event.callback_query.from_user

        # Update last_seen_at
        if user and "session" in data:
            session: AsyncSession = data["session"]
            await session.execute(
                update(User)
                .where(User.telegram_id == user.id)
                .values(last_seen_at=datetime.now(UTC))
            )
            # Commit handled by database middleware

        return await handler(event, data)
```

### 2.4 Регистрация middleware

**Файл:** `/var/www/biotact/packages/bot/bot/middlewares/__init__.py`

```python
from bot.middlewares.activity import ActivityMiddleware
from bot.middlewares.database import DatabaseMiddleware
from bot.middlewares.logging import LoggingMiddleware

__all__ = [
    "ActivityMiddleware",
    "DatabaseMiddleware",
    "LoggingMiddleware",
]
```

**Файл:** `/var/www/biotact/packages/bot/bot/__main__.py`

```python
# Добавить в setup middleware:
from bot.middlewares import ActivityMiddleware

# После DatabaseMiddleware:
dp.message.middleware(ActivityMiddleware())
dp.callback_query.middleware(ActivityMiddleware())
```

### 2.5 Расширение Analytics API

**Файл:** `/var/www/biotact/packages/api/src/analytics/schemas.py`

```python
# Добавить новые поля в DashboardStats:
class DashboardStats(BaseModel):
    # ... существующие поля ...

    # Новые метрики активности
    total_users: int
    active_users_7d: int
    active_users_30d: int
    new_users_today: int
    new_users_7d: int
```

**Файл:** `/var/www/biotact/packages/api/src/analytics/service.py`

```python
# Добавить в get_dashboard_stats():

from datetime import datetime, timedelta
from sqlalchemy import func

async def get_dashboard_stats(db: AsyncSession, days: int = 30) -> DashboardStats:
    # ... существующий код ...

    now = datetime.now()

    # Total users
    total_users = await db.scalar(
        select(func.count(User.id))
    )

    # Active users (last 7 days)
    active_7d = await db.scalar(
        select(func.count(User.id)).where(
            User.last_seen_at >= now - timedelta(days=7)
        )
    )

    # Active users (last 30 days)
    active_30d = await db.scalar(
        select(func.count(User.id)).where(
            User.last_seen_at >= now - timedelta(days=30)
        )
    )

    # New users today
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    new_today = await db.scalar(
        select(func.count(User.id)).where(
            User.created_at >= today_start
        )
    )

    # New users last 7 days
    new_7d = await db.scalar(
        select(func.count(User.id)).where(
            User.created_at >= now - timedelta(days=7)
        )
    )

    return DashboardStats(
        # ... существующие поля ...
        total_users=total_users or 0,
        active_users_7d=active_7d or 0,
        active_users_30d=active_30d or 0,
        new_users_today=new_today or 0,
        new_users_7d=new_7d or 0,
    )
```

---

## 3. Порядок выполнения

### Шаг 1: Миграция БД
```bash
ssh biotact-miniapp "PGPASSWORD=biotact_secure_2024 psql -h localhost -U biotact -d biotact_db -c \"
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ;
UPDATE users SET last_seen_at = COALESCE(updated_at, created_at) WHERE last_seen_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_users_last_seen ON users(last_seen_at);
\""
```

### Шаг 2: Обновить модель User (Bot)
- Файл: `/var/www/biotact/packages/bot/bot/models/user.py`
- Добавить поле `last_seen_at`

### Шаг 3: Создать ActivityMiddleware
- Создать файл: `/var/www/biotact/packages/bot/bot/middlewares/activity.py`

### Шаг 4: Зарегистрировать middleware
- Обновить: `/var/www/biotact/packages/bot/bot/middlewares/__init__.py`
- Обновить: `/var/www/biotact/packages/bot/bot/__main__.py`

### Шаг 5: Обновить модель User (API)
- Файл: `/var/www/biotact/packages/api/src/users/models.py`
- Добавить поле `last_seen_at`

### Шаг 6: Расширить Analytics schemas
- Файл: `/var/www/biotact/packages/api/src/analytics/schemas.py`

### Шаг 7: Расширить Analytics service
- Файл: `/var/www/biotact/packages/api/src/analytics/service.py`

### Шаг 8: Перезапустить сервисы
```bash
ssh biotact-miniapp "pm2 restart bot api"
```

### Шаг 9: Проверить
```bash
# Проверить миграцию
ssh biotact-miniapp "PGPASSWORD=biotact_secure_2024 psql -h localhost -U biotact -d biotact_db -c \"
SELECT id, telegram_id, first_name, last_seen_at FROM users ORDER BY last_seen_at DESC LIMIT 5;
\""

# Проверить API
curl -H "Authorization: Bearer <token>" https://api.biotact.uz/analytics/dashboard
```

---

## 4. Результат

После реализации dashboard будет показывать:

| Метрика | Описание |
|---------|----------|
| total_users | Всего пользователей |
| active_users_7d | Активных за 7 дней |
| active_users_30d | Активных за 30 дней |
| new_users_today | Новых сегодня |
| new_users_7d | Новых за неделю |

Плюс существующие метрики:
- total_revenue
- total_orders
- pending_orders
- completed_orders
- revenue_data (график)
- recent_orders
- top_products
- order_status_distribution

---

## 5. Риски и откат

### Риски
- **Низкий:** Миграция добавляет nullable поле, не ломает существующий код
- **Низкий:** Middleware выполняет простой UPDATE

### Откат
```sql
-- Если нужно откатить
ALTER TABLE users DROP COLUMN last_seen_at;
DROP INDEX IF EXISTS idx_users_last_seen;
```

```bash
# Удалить middleware и перезапустить
pm2 restart bot api
```

---

## 6. Будущие улучшения (при росте)

При достижении 500+ пользователей:
- Добавить таблицу `events`
- Воронка конверсии
- Базовый retention

При достижении 2000+ пользователей:
- Полное event tracking
- Когортный анализ
- Еженедельные отчёты в Telegram

---

**Документ подготовлен:** Claude
**Проект:** claude-agent (DevOps Bot)
