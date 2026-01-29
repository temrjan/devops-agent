# POSTGRESQL GUIDE
## Для Claude Code — PostgreSQL

> **Цель:** Единый стиль работы с PostgreSQL  
> **Референс:** PostgreSQL официальная документация  
> **Версия:** PostgreSQL 15+

---

## 🎯 КЛЮЧЕВЫЕ ПРИНЦИПЫ

```
ВСЕГДА                              НИКОГДА
────────────────────────────────    ────────────────────────────────
✓ Индексы на WHERE/JOIN/ORDER BY   ✗ Индексы на всё подряд
✓ EXPLAIN ANALYZE перед оптимизацией ✗ Слепая оптимизация
✓ snake_case для имён               ✗ CamelCase / PascalCase
✓ UUID или BIGSERIAL для PK         ✗ INTEGER для PK в prod
✓ TIMESTAMPTZ для времени           ✗ TIMESTAMP без timezone
✓ NOT NULL где возможно             ✗ Nullable колонки без причины
✓ Foreign Keys                      ✗ Связи только в коде
✓ Migrations (Prisma/Alembic)       ✗ Ручное изменение схемы
✓ Connection pooling (PgBouncer)    ✗ Прямые подключения в prod
```

---

## 📋 NAMING CONVENTIONS

```sql
-- ═══════════════════════════════════════════════════════════════════
-- Таблицы: plural, snake_case
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE users (...);
CREATE TABLE order_items (...);
CREATE TABLE user_permissions (...);

-- ═══════════════════════════════════════════════════════════════════
-- Колонки: snake_case
-- ═══════════════════════════════════════════════════════════════════
user_id, first_name, created_at, is_active

-- ═══════════════════════════════════════════════════════════════════
-- Primary Keys: id или <table>_id
-- ═══════════════════════════════════════════════════════════════════
id BIGSERIAL PRIMARY KEY
-- или
user_id UUID PRIMARY KEY DEFAULT gen_random_uuid()

-- ═══════════════════════════════════════════════════════════════════
-- Foreign Keys: <referenced_table>_id
-- ═══════════════════════════════════════════════════════════════════
user_id BIGINT REFERENCES users(id)
category_id UUID REFERENCES categories(id)

-- ═══════════════════════════════════════════════════════════════════
-- Индексы: idx_<table>_<columns>
-- ═══════════════════════════════════════════════════════════════════
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_orders_user_id_created_at ON orders(user_id, created_at);

-- ═══════════════════════════════════════════════════════════════════
-- Unique Constraints: uq_<table>_<columns>
-- ═══════════════════════════════════════════════════════════════════
CONSTRAINT uq_users_email UNIQUE (email)

-- ═══════════════════════════════════════════════════════════════════
-- Check Constraints: ck_<table>_<description>
-- ═══════════════════════════════════════════════════════════════════
CONSTRAINT ck_products_price_positive CHECK (price > 0)

-- ═══════════════════════════════════════════════════════════════════
-- Foreign Key Constraints: fk_<table>_<referenced_table>
-- ═══════════════════════════════════════════════════════════════════
CONSTRAINT fk_orders_users FOREIGN KEY (user_id) REFERENCES users(id)
```

---

## 📊 ТИПЫ ДАННЫХ

### Рекомендуемые типы

```sql
-- ═══════════════════════════════════════════════════════════════════
-- Идентификаторы
-- ═══════════════════════════════════════════════════════════════════
id BIGSERIAL PRIMARY KEY                    -- Авто-инкремент (до 9.2 квинтиллионов)
id UUID PRIMARY KEY DEFAULT gen_random_uuid() -- UUID v4 (распределённые системы)

-- ═══════════════════════════════════════════════════════════════════
-- Числа
-- ═══════════════════════════════════════════════════════════════════
age SMALLINT                                -- -32,768 до 32,767
count INTEGER                               -- -2B до 2B
big_count BIGINT                            -- Очень большие числа
price NUMERIC(10, 2)                        -- Точные деньги: 12345678.99
rating REAL                                 -- 6 знаков точности (float4)
score DOUBLE PRECISION                      -- 15 знаков точности (float8)

-- ═══════════════════════════════════════════════════════════════════
-- Строки
-- ═══════════════════════════════════════════════════════════════════
email VARCHAR(255)                          -- Ограниченная длина
name TEXT                                   -- Неограниченная длина
code CHAR(3)                                -- Фиксированная длина (ISO коды)

-- ═══════════════════════════════════════════════════════════════════
-- Дата и время (ВСЕГДА с timezone!)
-- ═══════════════════════════════════════════════════════════════════
created_at TIMESTAMPTZ DEFAULT NOW()        -- С timezone (рекомендуется)
birth_date DATE                             -- Только дата
start_time TIME                             -- Только время
duration INTERVAL                           -- Промежуток времени

-- ═══════════════════════════════════════════════════════════════════
-- Boolean
-- ═══════════════════════════════════════════════════════════════════
is_active BOOLEAN DEFAULT true
is_verified BOOLEAN NOT NULL DEFAULT false

-- ═══════════════════════════════════════════════════════════════════
-- JSON
-- ═══════════════════════════════════════════════════════════════════
metadata JSONB                              -- Бинарный JSON (быстрее для запросов)
settings JSON                               -- Текстовый JSON (сохраняет порядок)

-- ═══════════════════════════════════════════════════════════════════
-- Массивы
-- ═══════════════════════════════════════════════════════════════════
tags TEXT[]                                 -- Массив строк
scores INTEGER[]                            -- Массив чисел

-- ═══════════════════════════════════════════════════════════════════
-- Enum
-- ═══════════════════════════════════════════════════════════════════
CREATE TYPE order_status AS ENUM ('pending', 'processing', 'completed', 'cancelled');
status order_status DEFAULT 'pending'
```

### Типы для специальных случаев

```sql
-- IP адреса
ip_address INET                             -- IPv4 или IPv6

-- MAC адреса
mac_address MACADDR

-- Диапазоны
price_range INT4RANGE                       -- [100, 500)
booking_period TSTZRANGE                    -- Временной диапазон

-- Геометрия (с PostGIS)
location GEOMETRY(POINT, 4326)              -- GPS координаты
area GEOMETRY(POLYGON, 4326)                -- Полигон
```

---

## 🏗️ SCHEMA DESIGN

### Базовая таблица

```sql
CREATE TABLE users (
    -- Primary Key
    id BIGSERIAL PRIMARY KEY,
    
    -- или UUID
    -- id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Данные
    email VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    
    -- Статус
    is_active BOOLEAN NOT NULL DEFAULT true,
    is_verified BOOLEAN NOT NULL DEFAULT false,
    role VARCHAR(50) NOT NULL DEFAULT 'user',
    
    -- Метаданные
    metadata JSONB DEFAULT '{}',
    
    -- Timestamps (ВСЕГДА!)
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT uq_users_email UNIQUE (email),
    CONSTRAINT ck_users_email_format CHECK (email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')
);

-- Индексы
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_created_at ON users(created_at DESC);
CREATE INDEX idx_users_is_active ON users(is_active) WHERE is_active = true;
```

### Таблица с Foreign Keys

```sql
CREATE TABLE orders (
    id BIGSERIAL PRIMARY KEY,
    
    -- Foreign Keys
    user_id BIGINT NOT NULL,
    
    -- Данные
    order_number VARCHAR(50) NOT NULL,
    status order_status NOT NULL DEFAULT 'pending',
    total_amount NUMERIC(12, 2) NOT NULL,
    currency CHAR(3) NOT NULL DEFAULT 'USD',
    
    -- Адрес (денормализация для истории)
    shipping_address JSONB NOT NULL,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    
    -- Constraints
    CONSTRAINT fk_orders_users 
        FOREIGN KEY (user_id) 
        REFERENCES users(id) 
        ON DELETE RESTRICT 
        ON UPDATE CASCADE,
    CONSTRAINT uq_orders_order_number UNIQUE (order_number),
    CONSTRAINT ck_orders_total_positive CHECK (total_amount >= 0)
);

-- Индексы
CREATE INDEX idx_orders_user_id ON orders(user_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_created_at ON orders(created_at DESC);
CREATE INDEX idx_orders_user_status ON orders(user_id, status);
```

### Many-to-Many

```sql
-- Таблица связей
CREATE TABLE user_roles (
    user_id BIGINT NOT NULL,
    role_id BIGINT NOT NULL,
    
    -- Дополнительные данные связи
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    assigned_by BIGINT,
    
    -- Composite Primary Key
    PRIMARY KEY (user_id, role_id),
    
    -- Foreign Keys
    CONSTRAINT fk_user_roles_users 
        FOREIGN KEY (user_id) 
        REFERENCES users(id) 
        ON DELETE CASCADE,
    CONSTRAINT fk_user_roles_roles 
        FOREIGN KEY (role_id) 
        REFERENCES roles(id) 
        ON DELETE CASCADE
);

-- Индексы для обратного поиска
CREATE INDEX idx_user_roles_role_id ON user_roles(role_id);
```

---

## 🔍 ИНДЕКСЫ

### Типы индексов

```sql
-- ═══════════════════════════════════════════════════════════════════
-- B-Tree (default) — для =, <, >, <=, >=, BETWEEN, IN, IS NULL
-- ═══════════════════════════════════════════════════════════════════
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_orders_created_at ON orders(created_at DESC);

-- ═══════════════════════════════════════════════════════════════════
-- Hash — только для = (быстрее B-Tree для equality)
-- ═══════════════════════════════════════════════════════════════════
CREATE INDEX idx_users_email_hash ON users USING hash(email);

-- ═══════════════════════════════════════════════════════════════════
-- GIN — для JSONB, массивов, полнотекстового поиска
-- ═══════════════════════════════════════════════════════════════════
CREATE INDEX idx_products_tags ON products USING gin(tags);
CREATE INDEX idx_users_metadata ON users USING gin(metadata);
CREATE INDEX idx_posts_search ON posts USING gin(to_tsvector('russian', title || ' ' || content));

-- ═══════════════════════════════════════════════════════════════════
-- GiST — для геометрии, диапазонов, полнотекстового поиска
-- ═══════════════════════════════════════════════════════════════════
CREATE INDEX idx_locations_point ON locations USING gist(coordinates);
CREATE INDEX idx_bookings_period ON bookings USING gist(booking_period);

-- ═══════════════════════════════════════════════════════════════════
-- BRIN — для больших таблиц с естественной сортировкой (time-series)
-- ═══════════════════════════════════════════════════════════════════
CREATE INDEX idx_events_created_at ON events USING brin(created_at);
-- Очень маленький размер, идеален для логов
```

### Специальные индексы

```sql
-- ═══════════════════════════════════════════════════════════════════
-- Partial Index — индекс с условием
-- ═══════════════════════════════════════════════════════════════════
CREATE INDEX idx_orders_pending 
    ON orders(created_at) 
    WHERE status = 'pending';
-- Меньше размер, быстрее для частых запросов

-- ═══════════════════════════════════════════════════════════════════
-- Unique Index
-- ═══════════════════════════════════════════════════════════════════
CREATE UNIQUE INDEX idx_users_email_unique ON users(email);

-- Partial Unique (например, один активный на пользователя)
CREATE UNIQUE INDEX idx_subscriptions_active_user 
    ON subscriptions(user_id) 
    WHERE is_active = true;

-- ═══════════════════════════════════════════════════════════════════
-- Composite Index (порядок важен!)
-- ═══════════════════════════════════════════════════════════════════
CREATE INDEX idx_orders_user_status_date 
    ON orders(user_id, status, created_at DESC);
-- Работает для: (user_id), (user_id, status), (user_id, status, created_at)
-- НЕ работает для: (status), (created_at), (status, created_at)

-- ═══════════════════════════════════════════════════════════════════
-- Covering Index (INCLUDE) — Index-Only Scan
-- ═══════════════════════════════════════════════════════════════════
CREATE INDEX idx_orders_user_include 
    ON orders(user_id) 
    INCLUDE (status, total_amount);
-- Запрос SELECT status, total_amount FROM orders WHERE user_id = 1
-- не обращается к таблице (Index Only Scan)

-- ═══════════════════════════════════════════════════════════════════
-- Expression Index
-- ═══════════════════════════════════════════════════════════════════
CREATE INDEX idx_users_email_lower ON users(LOWER(email));
-- Для запросов: WHERE LOWER(email) = 'test@example.com'

CREATE INDEX idx_orders_year ON orders((EXTRACT(YEAR FROM created_at)));
-- Для запросов: WHERE EXTRACT(YEAR FROM created_at) = 2024

-- ═══════════════════════════════════════════════════════════════════
-- JSONB индексы
-- ═══════════════════════════════════════════════════════════════════
-- Весь JSONB (для @>, ?, ?&, ?|)
CREATE INDEX idx_users_metadata_gin ON users USING gin(metadata);

-- Конкретный путь
CREATE INDEX idx_users_metadata_country 
    ON users((metadata->>'country'));

-- jsonb_path_ops (меньше, быстрее для @>)
CREATE INDEX idx_users_metadata_path 
    ON users USING gin(metadata jsonb_path_ops);
```

### Concurrent Index (без блокировки)

```sql
-- ОБЯЗАТЕЛЬНО для production!
CREATE INDEX CONCURRENTLY idx_users_email ON users(email);

-- Удаление
DROP INDEX CONCURRENTLY idx_users_email;
```

---

## 📈 QUERY OPTIMIZATION

### EXPLAIN ANALYZE

```sql
-- Базовый анализ
EXPLAIN ANALYZE 
SELECT * FROM orders WHERE user_id = 123;

-- С буферами и таймингами
EXPLAIN (ANALYZE, BUFFERS, TIMING, FORMAT TEXT) 
SELECT * FROM orders WHERE user_id = 123;

-- JSON формат для инструментов
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) 
SELECT * FROM orders WHERE user_id = 123;
```

### Что искать в плане

```
Seq Scan        → Нужен индекс?
Nested Loop     → Много итераций? Join на большие таблицы?
Hash Join       → ОК для больших таблиц
Merge Join      → ОК если данные отсортированы
Sort            → Нужен индекс с ORDER BY?
Filter          → Условие после чтения данных (плохо)
Index Cond      → Условие использует индекс (хорошо)
Rows Removed    → Много отфильтровано? Partial index?
```

### Оптимизация запросов

```sql
-- ═══════════════════════════════════════════════════════════════════
-- ПЛОХО: SELECT *
-- ═══════════════════════════════════════════════════════════════════
SELECT * FROM users WHERE id = 1;

-- ХОРОШО: только нужные колонки
SELECT id, email, first_name FROM users WHERE id = 1;

-- ═══════════════════════════════════════════════════════════════════
-- ПЛОХО: функция на колонке (не использует индекс)
-- ═══════════════════════════════════════════════════════════════════
SELECT * FROM users WHERE LOWER(email) = 'test@example.com';

-- ХОРОШО: expression index или нормализация данных
CREATE INDEX idx_users_email_lower ON users(LOWER(email));
-- Или храните email в lower case

-- ═══════════════════════════════════════════════════════════════════
-- ПЛОХО: OR (иногда не использует индекс)
-- ═══════════════════════════════════════════════════════════════════
SELECT * FROM users WHERE status = 'active' OR status = 'pending';

-- ХОРОШО: IN
SELECT * FROM users WHERE status IN ('active', 'pending');

-- ═══════════════════════════════════════════════════════════════════
-- ПЛОХО: LIKE с % в начале
-- ═══════════════════════════════════════════════════════════════════
SELECT * FROM products WHERE name LIKE '%phone%';

-- ХОРОШО: Full-Text Search
SELECT * FROM products 
WHERE to_tsvector('english', name) @@ to_tsquery('english', 'phone');

-- ═══════════════════════════════════════════════════════════════════
-- ПЛОХО: N+1 проблема
-- ═══════════════════════════════════════════════════════════════════
-- В коде: for user in users: get_orders(user.id)

-- ХОРОШО: JOIN или batch
SELECT u.*, o.* 
FROM users u 
LEFT JOIN orders o ON o.user_id = u.id 
WHERE u.id IN (1, 2, 3, 4, 5);

-- ═══════════════════════════════════════════════════════════════════
-- Пагинация: OFFSET плохо масштабируется
-- ═══════════════════════════════════════════════════════════════════
-- ПЛОХО для больших offset
SELECT * FROM orders ORDER BY created_at DESC LIMIT 20 OFFSET 10000;

-- ХОРОШО: Cursor-based pagination
SELECT * FROM orders 
WHERE created_at < '2024-01-15 10:00:00' 
ORDER BY created_at DESC 
LIMIT 20;
```

---

## 🔄 ТРАНЗАКЦИИ

### Уровни изоляции

```sql
-- Read Committed (default)
BEGIN;
-- Видит committed изменения других транзакций
COMMIT;

-- Repeatable Read
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;
-- Snapshot на момент первого запроса
COMMIT;

-- Serializable
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;
-- Полная изоляция, возможны serialization failures
COMMIT;
```

### Примеры

```sql
-- Перевод денег
BEGIN;

UPDATE accounts SET balance = balance - 100 WHERE id = 1;
UPDATE accounts SET balance = balance + 100 WHERE id = 2;

-- Проверка
SELECT balance FROM accounts WHERE id IN (1, 2);

COMMIT;
-- Или ROLLBACK; при ошибке

-- ═══════════════════════════════════════════════════════════════════
-- Savepoints
-- ═══════════════════════════════════════════════════════════════════
BEGIN;

INSERT INTO orders (...) VALUES (...);
SAVEPOINT before_items;

INSERT INTO order_items (...) VALUES (...);
-- Ошибка?
ROLLBACK TO SAVEPOINT before_items;

INSERT INTO order_items (...) VALUES (...);  -- Повторяем

COMMIT;

-- ═══════════════════════════════════════════════════════════════════
-- Advisory Locks (application-level)
-- ═══════════════════════════════════════════════════════════════════
-- Получить блокировку (ждёт если занята)
SELECT pg_advisory_lock(12345);

-- Попробовать получить (не ждёт)
SELECT pg_try_advisory_lock(12345);  -- true/false

-- Освободить
SELECT pg_advisory_unlock(12345);
```

---

## 🛠️ ПОЛЕЗНЫЕ ФУНКЦИИ

### Timestamps

```sql
-- Автоматическое обновление updated_at
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();
```

### UUID

```sql
-- Генерация UUID v4
SELECT gen_random_uuid();

-- UUID v7 (time-ordered, требует расширение)
CREATE EXTENSION IF NOT EXISTS pg_uuidv7;
SELECT uuid_generate_v7();
```

### JSONB операции

```sql
-- Получить значение
SELECT metadata->>'country' FROM users;          -- как text
SELECT metadata->'address'->'city' FROM users;   -- как jsonb

-- Проверка ключа
SELECT * FROM users WHERE metadata ? 'country';

-- Содержит
SELECT * FROM users WHERE metadata @> '{"country": "US"}';

-- Обновление
UPDATE users 
SET metadata = metadata || '{"verified": true}'
WHERE id = 1;

-- Удаление ключа
UPDATE users 
SET metadata = metadata - 'temp_field'
WHERE id = 1;

-- Глубокое обновление
UPDATE users 
SET metadata = jsonb_set(metadata, '{address,city}', '"New York"')
WHERE id = 1;
```

### Full-Text Search

```sql
-- Добавляем колонку для поиска
ALTER TABLE products ADD COLUMN search_vector tsvector;

-- Заполняем
UPDATE products 
SET search_vector = to_tsvector('russian', coalesce(name, '') || ' ' || coalesce(description, ''));

-- Индекс
CREATE INDEX idx_products_search ON products USING gin(search_vector);

-- Триггер для автообновления
CREATE TRIGGER trigger_products_search
    BEFORE INSERT OR UPDATE ON products
    FOR EACH ROW
    EXECUTE FUNCTION tsvector_update_trigger(
        search_vector, 'pg_catalog.russian', name, description
    );

-- Поиск
SELECT * FROM products 
WHERE search_vector @@ to_tsquery('russian', 'телефон & samsung');

-- С рангом
SELECT *, ts_rank(search_vector, query) AS rank
FROM products, to_tsquery('russian', 'телефон') query
WHERE search_vector @@ query
ORDER BY rank DESC;
```

---

## 📊 МОНИТОРИНГ

### Полезные запросы

```sql
-- ═══════════════════════════════════════════════════════════════════
-- Размер таблиц и индексов
-- ═══════════════════════════════════════════════════════════════════
SELECT 
    relname AS table_name,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size,
    pg_size_pretty(pg_relation_size(relid)) AS table_size,
    pg_size_pretty(pg_total_relation_size(relid) - pg_relation_size(relid)) AS index_size
FROM pg_catalog.pg_statio_user_tables
ORDER BY pg_total_relation_size(relid) DESC;

-- ═══════════════════════════════════════════════════════════════════
-- Неиспользуемые индексы
-- ═══════════════════════════════════════════════════════════════════
SELECT 
    schemaname || '.' || relname AS table,
    indexrelname AS index,
    pg_size_pretty(pg_relation_size(i.indexrelid)) AS index_size,
    idx_scan AS scans
FROM pg_stat_user_indexes ui
JOIN pg_index i ON ui.indexrelid = i.indexrelid
WHERE NOT indisunique  -- Не уникальные
  AND idx_scan < 50     -- Мало сканирований
ORDER BY pg_relation_size(i.indexrelid) DESC;

-- ═══════════════════════════════════════════════════════════════════
-- Медленные запросы (требует pg_stat_statements)
-- ═══════════════════════════════════════════════════════════════════
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

SELECT 
    calls,
    round(total_exec_time::numeric, 2) AS total_time_ms,
    round(mean_exec_time::numeric, 2) AS mean_time_ms,
    round((100 * total_exec_time / sum(total_exec_time) OVER ())::numeric, 2) AS percent,
    query
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;

-- ═══════════════════════════════════════════════════════════════════
-- Активные подключения
-- ═══════════════════════════════════════════════════════════════════
SELECT 
    pid,
    usename,
    application_name,
    client_addr,
    state,
    query_start,
    query
FROM pg_stat_activity
WHERE state != 'idle'
ORDER BY query_start;

-- ═══════════════════════════════════════════════════════════════════
-- Блокировки
-- ═══════════════════════════════════════════════════════════════════
SELECT 
    blocked_locks.pid AS blocked_pid,
    blocked_activity.usename AS blocked_user,
    blocking_locks.pid AS blocking_pid,
    blocking_activity.usename AS blocking_user,
    blocked_activity.query AS blocked_query
FROM pg_catalog.pg_locks blocked_locks
JOIN pg_catalog.pg_stat_activity blocked_activity 
    ON blocked_activity.pid = blocked_locks.pid
JOIN pg_catalog.pg_locks blocking_locks 
    ON blocking_locks.locktype = blocked_locks.locktype
    AND blocking_locks.database IS NOT DISTINCT FROM blocked_locks.database
    AND blocking_locks.relation IS NOT DISTINCT FROM blocked_locks.relation
    AND blocking_locks.page IS NOT DISTINCT FROM blocked_locks.page
    AND blocking_locks.tuple IS NOT DISTINCT FROM blocked_locks.tuple
    AND blocking_locks.virtualxid IS NOT DISTINCT FROM blocked_locks.virtualxid
    AND blocking_locks.transactionid IS NOT DISTINCT FROM blocked_locks.transactionid
    AND blocking_locks.classid IS NOT DISTINCT FROM blocked_locks.classid
    AND blocking_locks.objid IS NOT DISTINCT FROM blocked_locks.objid
    AND blocking_locks.objsubid IS NOT DISTINCT FROM blocked_locks.objsubid
    AND blocking_locks.pid != blocked_locks.pid
JOIN pg_catalog.pg_stat_activity blocking_activity 
    ON blocking_activity.pid = blocking_locks.pid
WHERE NOT blocked_locks.granted;

-- ═══════════════════════════════════════════════════════════════════
-- Cache hit ratio (должен быть > 99%)
-- ═══════════════════════════════════════════════════════════════════
SELECT 
    round(100.0 * sum(blks_hit) / nullif(sum(blks_hit) + sum(blks_read), 0), 2) AS cache_hit_ratio
FROM pg_stat_database;
```

---

## 🔧 MAINTENANCE

```sql
-- ═══════════════════════════════════════════════════════════════════
-- VACUUM (очистка мёртвых строк)
-- ═══════════════════════════════════════════════════════════════════
VACUUM orders;              -- Обычный vacuum
VACUUM FULL orders;         -- Полная перестройка (блокирует таблицу!)
VACUUM ANALYZE orders;      -- + обновление статистики

-- ═══════════════════════════════════════════════════════════════════
-- ANALYZE (обновление статистики для планировщика)
-- ═══════════════════════════════════════════════════════════════════
ANALYZE orders;
ANALYZE;  -- Вся БД

-- ═══════════════════════════════════════════════════════════════════
-- REINDEX (перестройка индексов)
-- ═══════════════════════════════════════════════════════════════════
REINDEX INDEX CONCURRENTLY idx_orders_user_id;
REINDEX TABLE CONCURRENTLY orders;

-- ═══════════════════════════════════════════════════════════════════
-- Bloat check
-- ═══════════════════════════════════════════════════════════════════
SELECT 
    schemaname, tablename,
    pg_size_pretty(pg_total_relation_size(schemaname || '.' || tablename)) AS total_size,
    round(100 * n_dead_tup::numeric / nullif(n_live_tup + n_dead_tup, 0), 2) AS dead_ratio
FROM pg_stat_user_tables
WHERE n_dead_tup > 1000
ORDER BY n_dead_tup DESC;
```

---

## 💾 BACKUP

```bash
# ═══════════════════════════════════════════════════════════════════
# pg_dump (логический backup)
# ═══════════════════════════════════════════════════════════════════

# Полный backup
pg_dump -U postgres -Fc mydb > backup.dump

# Только схема
pg_dump -U postgres -s mydb > schema.sql

# Только данные
pg_dump -U postgres -a mydb > data.sql

# Конкретные таблицы
pg_dump -U postgres -t users -t orders mydb > partial.dump

# ═══════════════════════════════════════════════════════════════════
# pg_restore
# ═══════════════════════════════════════════════════════════════════

# Восстановление
pg_restore -U postgres -d mydb backup.dump

# В новую БД
createdb -U postgres newdb
pg_restore -U postgres -d newdb backup.dump

# ═══════════════════════════════════════════════════════════════════
# Continuous archiving (WAL)
# ═══════════════════════════════════════════════════════════════════
# В postgresql.conf:
# archive_mode = on
# archive_command = 'cp %p /backup/wal/%f'
# wal_level = replica
```

---

## ✅ ЧЕКЛИСТ

```
SCHEMA DESIGN
□ snake_case для всех имён
□ BIGSERIAL или UUID для PK
□ TIMESTAMPTZ для времени
□ NOT NULL где возможно
□ Foreign Keys с ON DELETE/UPDATE
□ Check constraints для валидации
□ created_at, updated_at на всех таблицах

ИНДЕКСЫ
□ Индексы на FK колонках
□ Индексы на WHERE/JOIN/ORDER BY
□ GIN для JSONB и массивов
□ BRIN для time-series
□ Partial indexes для частых условий
□ CONCURRENTLY в production

ОПТИМИЗАЦИЯ
□ EXPLAIN ANALYZE для критичных запросов
□ Избегать SELECT *
□ Избегать функций на индексируемых колонках
□ Cursor pagination вместо OFFSET
□ Connection pooling (PgBouncer)

MAINTENANCE
□ autovacuum включён
□ pg_stat_statements для мониторинга
□ Регулярный ANALYZE
□ Мониторинг cache hit ratio (>99%)
□ Регулярные backups
```

---

## 🚀 БЫСТРЫЙ ПРОМПТ

```
PostgreSQL схема. Следуй postgresql.org/docs:

NAMING:
- snake_case везде
- Таблицы: plural (users, orders)
- PK: id BIGSERIAL или id UUID
- FK: <table>_id (user_id, order_id)
- Индексы: idx_<table>_<columns>

ТИПЫ:
- TIMESTAMPTZ для времени (НЕ TIMESTAMP!)
- NUMERIC(10,2) для денег
- JSONB для JSON (не JSON)
- TEXT вместо VARCHAR без ограничений

ОБЯЗАТЕЛЬНО:
✅ created_at TIMESTAMPTZ DEFAULT NOW()
✅ updated_at TIMESTAMPTZ с триггером
✅ Foreign Keys с ON DELETE
✅ Индексы на FK колонках
✅ NOT NULL по умолчанию
✅ CREATE INDEX CONCURRENTLY в prod

ИНДЕКСЫ:
- B-Tree: equality, range
- GIN: JSONB, arrays, FTS
- BRIN: time-series большие таблицы
- Partial: WHERE status = 'active'
```

---

**Версия:** 1.0  
**Дата:** 01.12.2025
