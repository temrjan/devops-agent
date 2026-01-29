# ТЗ: Аналитика BioTact MiniApp

**Сервер:** biotact-miniapp (ssh biotact-miniapp)
**БД:** PostgreSQL biotact_db
**Полный план:** docs/BIOTACT_ANALYTICS_PLAN.md

---

## Задача

Добавить отслеживание активности пользователей в BioTact MiniApp.

## Что сделать

### 1. Миграция БД
```sql
ALTER TABLE users ADD COLUMN last_seen_at TIMESTAMPTZ;
UPDATE users SET last_seen_at = updated_at;
CREATE INDEX idx_users_last_seen ON users(last_seen_at);
```

### 2. Бот: модель + middleware
- `/var/www/biotact/packages/bot/bot/models/user.py` — добавить `last_seen_at`
- Создать `/var/www/biotact/packages/bot/bot/middlewares/activity.py`
- Зарегистрировать в `__main__.py`

### 3. API: расширить analytics
- `/var/www/biotact/packages/api/src/users/models.py` — добавить `last_seen_at`
- `/var/www/biotact/packages/api/src/analytics/schemas.py` — новые поля
- `/var/www/biotact/packages/api/src/analytics/service.py` — новые метрики

### 4. Перезапуск
```bash
pm2 restart bot api
```

## Новые метрики

| Поле | Описание |
|------|----------|
| total_users | Всего пользователей |
| active_users_7d | Активных за 7 дней |
| active_users_30d | Активных за 30 дней |
| new_users_today | Новых сегодня |
| new_users_7d | Новых за неделю |

## Время: ~30 минут
