# FASTAPI GUIDE
## Для Claude Code — FastAPI

> **Цель:** Единый стиль разработки FastAPI приложений  
> **Референс:** FastAPI официальная документация + fastapi-best-practices  
> **Версия:** FastAPI 0.100+, Python 3.11+, Pydantic v2

---

## 🎯 КЛЮЧЕВЫЕ ПРИНЦИПЫ

```
ВСЕГДА                              НИКОГДА
────────────────────────────────    ────────────────────────────────
✓ Pydantic для валидации            ✗ Ручная валидация данных
✓ Depends() для DI                  ✗ Глобальные переменные
✓ async def для I/O операций        ✗ sync в async endpoints
✓ APIRouter для модульности         ✗ Всё в одном файле
✓ HTTPException для ошибок          ✗ Return {"error": ...}
✓ Alembic для миграций              ✗ Ручное создание таблиц
✓ Settings через Pydantic           ✗ Хардкод конфигов
✓ Типизация response_model          ✗ Возврат dict без типов
```

---

## 📁 СТРУКТУРА ПРОЕКТА

### Модульная структура (рекомендуется)

```
fastapi-project/
├── .env
├── .env.example
├── pyproject.toml
├── alembic.ini
├── alembic/                      # Миграции
│   ├── versions/
│   └── env.py
│
├── src/
│   ├── __init__.py
│   ├── main.py                   # FastAPI app
│   ├── config.py                 # Global settings
│   ├── database.py               # DB connection
│   │
│   ├── auth/                     # Auth module
│   │   ├── __init__.py
│   │   ├── router.py             # Endpoints
│   │   ├── schemas.py            # Pydantic models
│   │   ├── models.py             # SQLAlchemy models
│   │   ├── dependencies.py       # Module dependencies
│   │   ├── service.py            # Business logic
│   │   ├── exceptions.py         # Custom exceptions
│   │   ├── constants.py          # Constants
│   │   └── utils.py              # Helpers
│   │
│   ├── users/                    # Users module
│   │   ├── __init__.py
│   │   ├── router.py
│   │   ├── schemas.py
│   │   ├── models.py
│   │   ├── dependencies.py
│   │   └── service.py
│   │
│   ├── products/                 # Products module
│   │   └── ...
│   │
│   └── common/                   # Shared utilities
│       ├── __init__.py
│       ├── dependencies.py       # Global dependencies
│       ├── exceptions.py         # Global exceptions
│       └── pagination.py         # Pagination helpers
│
└── tests/
    ├── __init__.py
    ├── conftest.py               # pytest fixtures
    ├── test_auth.py
    └── test_users.py
```

---

## ⚙️ КОНФИГУРАЦИЯ

### Pydantic Settings

```python
# src/config.py

from functools import lru_cache
from pydantic import SecretStr, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    
    # App
    app_name: str = "FastAPI App"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    
    # Database
    database_url: PostgresDsn
    database_echo: bool = False
    
    # Redis
    redis_url: str = "redis://localhost:6379/0"
    
    # Auth
    secret_key: SecretStr
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    algorithm: str = "HS256"
    
    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]
    
    @field_validator("cors_origins", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v):
        if isinstance(v, str):
            return [i.strip() for i in v.split(",")]
        return v


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()


settings = get_settings()
```

### Main Application

```python
# src/main.py

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.database import engine, Base

# Import routers
from src.auth.router import router as auth_router
from src.users.router import router as users_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    # async with engine.begin() as conn:
    #     await conn.run_sync(Base.metadata.create_all)
    
    yield
    
    # Shutdown
    await engine.dispose()


def create_app() -> FastAPI:
    """Application factory."""
    
    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        lifespan=lifespan,
        # OpenAPI docs
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )
    
    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include routers
    app.include_router(
        auth_router,
        prefix=f"{settings.api_v1_prefix}/auth",
        tags=["auth"],
    )
    app.include_router(
        users_router,
        prefix=f"{settings.api_v1_prefix}/users",
        tags=["users"],
    )
    
    return app


app = create_app()


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
```

---

## 🗄️ DATABASE

### SQLAlchemy Async Setup

```python
# src/database.py

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from src.config import settings


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


# Async engine
engine = create_async_engine(
    str(settings.database_url),
    echo=settings.database_echo,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

# Session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting async session."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
```

### Models

```python
# src/users/models.py

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class User(Base):
    """User model."""
    
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
    )
    hashed_password: Mapped[str] = mapped_column(String(255))
    
    first_name: Mapped[Optional[str]] = mapped_column(String(100))
    last_name: Mapped[Optional[str]] = mapped_column(String(100))
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    
    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email})>"
```

---

## 📋 PYDANTIC SCHEMAS

```python
# src/users/schemas.py

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, ConfigDict, field_validator


# ═══════════════════════════════════════════════════════════════════
# Base Schemas
# ═══════════════════════════════════════════════════════════════════

class UserBase(BaseModel):
    """Base user schema."""
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class UserCreate(UserBase):
    """Schema for creating a user."""
    password: str
    
    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class UserUpdate(BaseModel):
    """Schema for updating a user."""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[EmailStr] = None


# ═══════════════════════════════════════════════════════════════════
# Response Schemas
# ═══════════════════════════════════════════════════════════════════

class UserResponse(UserBase):
    """User response schema."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    is_active: bool
    is_verified: bool
    created_at: datetime


class UserListResponse(BaseModel):
    """Paginated user list response."""
    items: list[UserResponse]
    total: int
    page: int
    size: int
    pages: int


# ═══════════════════════════════════════════════════════════════════
# Auth Schemas
# ═══════════════════════════════════════════════════════════════════

class Token(BaseModel):
    """JWT token response."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    """JWT token payload."""
    sub: int  # user_id
    exp: datetime
    type: str  # access or refresh
```

---

## 🛤️ ROUTERS

```python
# src/users/router.py

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.users import service
from src.users.schemas import (
    UserCreate,
    UserUpdate,
    UserResponse,
    UserListResponse,
)
from src.users.dependencies import get_current_user, get_current_superuser
from src.users.models import User


router = APIRouter()


# ═══════════════════════════════════════════════════════════════════
# Type Aliases (для читаемости)
# ═══════════════════════════════════════════════════════════════════

DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
SuperUser = Annotated[User, Depends(get_current_superuser)]


# ═══════════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════════

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: CurrentUser):
    """Get current user info."""
    return current_user


@router.patch("/me", response_model=UserResponse)
async def update_current_user(
    update_data: UserUpdate,
    current_user: CurrentUser,
    db: DbSession,
):
    """Update current user."""
    return await service.update_user(db, current_user.id, update_data)


@router.get("", response_model=UserListResponse)
async def get_users(
    db: DbSession,
    current_user: SuperUser,  # Только для superuser
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    """Get paginated list of users."""
    return await service.get_users_paginated(db, page=page, size=size)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    db: DbSession,
    current_user: SuperUser,
):
    """Get user by ID."""
    user = await service.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    db: DbSession,
    current_user: SuperUser,
):
    """Delete user."""
    await service.delete_user(db, user_id)
```

---

## 🔌 DEPENDENCY INJECTION

### Global Dependencies

```python
# src/common/dependencies.py

from typing import Annotated

from fastapi import Depends, Query
from pydantic import BaseModel


class PaginationParams(BaseModel):
    """Pagination parameters."""
    page: int = 1
    size: int = 20
    
    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size


def get_pagination(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Items per page"),
) -> PaginationParams:
    """Get pagination parameters."""
    return PaginationParams(page=page, size=size)


# Type alias
Pagination = Annotated[PaginationParams, Depends(get_pagination)]
```

### Module Dependencies

```python
# src/users/dependencies.py

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.database import get_db
from src.users import service
from src.users.models import User
from src.users.schemas import TokenPayload


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Get current authenticated user."""
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[settings.algorithm],
        )
        token_data = TokenPayload(**payload)
        
        if token_data.type != "access":
            raise credentials_exception
            
    except JWTError:
        raise credentials_exception
    
    user = await service.get_user_by_id(db, token_data.sub)
    
    if not user:
        raise credentials_exception
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )
    
    return user


async def get_current_superuser(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Get current superuser."""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )
    return current_user


# ═══════════════════════════════════════════════════════════════════
# Dependency для валидации существования ресурса
# ═══════════════════════════════════════════════════════════════════

async def valid_user_id(
    user_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Validate that user exists and return it."""
    user = await service.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user
```

---

## 🔧 SERVICE LAYER

```python
# src/users/service.py

from typing import Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.users.models import User
from src.users.schemas import UserCreate, UserUpdate, UserListResponse
from src.auth.utils import get_password_hash


async def get_user_by_id(
    db: AsyncSession,
    user_id: int,
) -> Optional[User]:
    """Get user by ID."""
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    return result.scalar_one_or_none()


async def get_user_by_email(
    db: AsyncSession,
    email: str,
) -> Optional[User]:
    """Get user by email."""
    result = await db.execute(
        select(User).where(User.email == email)
    )
    return result.scalar_one_or_none()


async def create_user(
    db: AsyncSession,
    user_data: UserCreate,
) -> User:
    """Create new user."""
    user = User(
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        first_name=user_data.first_name,
        last_name=user_data.last_name,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


async def update_user(
    db: AsyncSession,
    user_id: int,
    update_data: UserUpdate,
) -> Optional[User]:
    """Update user."""
    user = await get_user_by_id(db, user_id)
    if not user:
        return None
    
    # Update only provided fields
    update_dict = update_data.model_dump(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(user, field, value)
    
    await db.flush()
    await db.refresh(user)
    return user


async def delete_user(
    db: AsyncSession,
    user_id: int,
) -> bool:
    """Delete user."""
    user = await get_user_by_id(db, user_id)
    if not user:
        return False
    
    await db.delete(user)
    return True


async def get_users_paginated(
    db: AsyncSession,
    page: int = 1,
    size: int = 20,
) -> UserListResponse:
    """Get paginated list of users."""
    
    # Count total
    count_result = await db.execute(select(func.count(User.id)))
    total = count_result.scalar_one()
    
    # Get items
    offset = (page - 1) * size
    result = await db.execute(
        select(User)
        .order_by(User.created_at.desc())
        .offset(offset)
        .limit(size)
    )
    items = list(result.scalars().all())
    
    # Calculate pages
    pages = (total + size - 1) // size
    
    return UserListResponse(
        items=items,
        total=total,
        page=page,
        size=size,
        pages=pages,
    )
```

---

## ❌ EXCEPTION HANDLING

```python
# src/common/exceptions.py

from fastapi import HTTPException, status


class NotFoundException(HTTPException):
    def __init__(self, detail: str = "Resource not found"):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail,
        )


class UnauthorizedException(HTTPException):
    def __init__(self, detail: str = "Not authenticated"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


class ForbiddenException(HTTPException):
    def __init__(self, detail: str = "Not enough permissions"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
        )


class ConflictException(HTTPException):
    def __init__(self, detail: str = "Resource already exists"):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        )
```

---

## 🔐 AUTH (JWT)

```python
# src/auth/utils.py

from datetime import datetime, timedelta
from jose import jwt
from passlib.context import CryptContext

from src.config import settings


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(subject: int) -> str:
    expire = datetime.utcnow() + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    return jwt.encode(
        {"sub": str(subject), "exp": expire, "type": "access"},
        settings.secret_key.get_secret_value(),
        algorithm=settings.algorithm,
    )


def create_refresh_token(subject: int) -> str:
    expire = datetime.utcnow() + timedelta(
        days=settings.refresh_token_expire_days
    )
    return jwt.encode(
        {"sub": str(subject), "exp": expire, "type": "refresh"},
        settings.secret_key.get_secret_value(),
        algorithm=settings.algorithm,
    )
```

---

## 🧪 TESTING

```python
# tests/conftest.py

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.main import app
from src.database import Base, get_db


TEST_DATABASE_URL = "postgresql+asyncpg://test:test@localhost:5432/test_db"

engine_test = create_async_engine(TEST_DATABASE_URL)
async_session_test = async_sessionmaker(engine_test, class_=AsyncSession)


async def override_get_db():
    async with async_session_test() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
```

---

## ✅ ЧЕКЛИСТ

```
СТРУКТУРА
□ Модульная структура (auth/, users/, ...)
□ router, schemas, models, service, dependencies
□ Pydantic Settings для конфигурации
□ Alembic для миграций

ENDPOINTS
□ response_model для типизации
□ Правильные HTTP status codes
□ Depends() для DI
□ Annotated для читаемости

DATABASE
□ Async SQLAlchemy
□ Session через dependency
□ select() вместо query()

БЕЗОПАСНОСТЬ
□ JWT authentication
□ bcrypt для паролей
□ CORS настроен
□ Secrets в .env
```

---

## 🚀 БЫСТРЫЙ ПРОМПТ

```
FastAPI приложение на Python 3.11+, Pydantic v2:

СТРУКТУРА: src/users/, src/auth/ — каждый модуль имеет
router.py, schemas.py, models.py, service.py, dependencies.py

ОБЯЗАТЕЛЬНО:
✅ async def для I/O endpoints
✅ Annotated[AsyncSession, Depends(get_db)]
✅ response_model=UserResponse
✅ HTTPException для ошибок
✅ ConfigDict(from_attributes=True) для ORM schemas

PYDANTIC V2: field_validator, model_dump(), model_config
DATABASE: AsyncSession, select(), await db.execute()
```

---

**Версия:** 1.0  
**Дата:** 01.12.2025
