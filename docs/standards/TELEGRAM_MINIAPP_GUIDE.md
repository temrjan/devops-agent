# TELEGRAM MINI APP GUIDE
## Для Claude Code — React + TypeScript + @twa-dev/sdk + @telegram-apps/telegram-ui

> **Цель:** Единый стиль разработки Telegram Mini Apps  
> **Референс:** Telegram Mini Apps docs, @twa-dev/sdk, @telegram-apps/telegram-ui  
> **Версии:** React 18+, TypeScript 5+, @twa-dev/sdk 8.x, @telegram-apps/telegram-ui 2.x

---

## 🎯 КЛЮЧЕВЫЕ ПРИНЦИПЫ

```
ВСЕГДА                              НИКОГДА
────────────────────────────────    ────────────────────────────────
✓ WebApp.ready() при старте         ✗ Забывать вызвать ready()
✓ AppRoot для telegram-ui           ✗ Компоненты без AppRoot
✓ Проверка isAvailable()            ✗ Вызов методов без проверки
✓ Валидация initData на backend     ✗ Доверять данным без проверки
✓ Адаптация под iOS/Android         ✗ Единый дизайн для всех платформ
✓ Telegram цветовая схема           ✗ Хардкод цветов
✓ Haptic feedback                   ✗ Игнорирование вибрации
✓ Safe area insets                  ✗ Контент под системными элементами
```

---

## 📁 СТРУКТУРА ПРОЕКТА

```
telegram-mini-app/
├── .env                          # Переменные окружения
├── .env.example
├── vite.config.ts                # Vite конфигурация
├── tsconfig.json
├── package.json
│
├── public/
│   └── index.html
│
├── src/
│   ├── main.tsx                  # Entry point
│   ├── App.tsx                   # Root component
│   │
│   ├── components/               # UI компоненты
│   │   ├── ui/                   # Базовые компоненты
│   │   │   ├── Button.tsx
│   │   │   └── Input.tsx
│   │   ├── features/             # Feature компоненты
│   │   │   ├── UserProfile.tsx
│   │   │   └── ProductCard.tsx
│   │   └── layouts/              # Layout компоненты
│   │       ├── MainLayout.tsx
│   │       └── ModalLayout.tsx
│   │
│   ├── pages/                    # Страницы/экраны
│   │   ├── HomePage.tsx
│   │   ├── ProfilePage.tsx
│   │   └── SettingsPage.tsx
│   │
│   ├── hooks/                    # Custom hooks
│   │   ├── useTelegram.ts        # Telegram SDK hooks
│   │   ├── useMainButton.ts
│   │   └── useBackButton.ts
│   │
│   ├── stores/                   # Zustand stores
│   │   ├── userStore.ts
│   │   └── appStore.ts
│   │
│   ├── services/                 # API и сервисы
│   │   ├── api.ts
│   │   └── telegram.ts
│   │
│   ├── lib/                      # Утилиты
│   │   ├── utils.ts
│   │   └── constants.ts
│   │
│   ├── types/                    # TypeScript типы
│   │   ├── telegram.ts
│   │   └── api.ts
│   │
│   └── styles/                   # Глобальные стили
│       └── global.css
│
└── backend/                      # Backend для валидации
    └── validate-init-data.ts
```

---

## 🚀 ИНИЦИАЛИЗАЦИЯ

### Установка зависимостей

```bash
# Создание проекта
npm create vite@latest my-tma -- --template react-ts

# Основные зависимости
npm install @twa-dev/sdk @telegram-apps/telegram-ui zustand

# Dev зависимости
npm install -D @vitejs/plugin-basic-ssl
```

### Vite конфигурация

```typescript
// vite.config.ts
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import basicSsl from '@vitejs/plugin-basic-ssl';

export default defineConfig({
  plugins: [
    react(),
    basicSsl(), // HTTPS для локальной разработки
  ],
  server: {
    host: true, // Доступ по IP для тестирования
    port: 5173,
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
  base: './', // Относительные пути для GitHub Pages
});
```

### Entry Point

```tsx
// src/main.tsx
import ReactDOM from 'react-dom/client';
import WebApp from '@twa-dev/sdk';
import { AppRoot } from '@telegram-apps/telegram-ui';

// Стили telegram-ui
import '@telegram-apps/telegram-ui/dist/styles.css';
import './styles/global.css';

import App from './App';

// ═══════════════════════════════════════════════════════════════════
// КРИТИЧЕСКИ ВАЖНО: Вызвать ready() как можно раньше
// ═══════════════════════════════════════════════════════════════════
WebApp.ready();

// Раскрыть на весь экран
WebApp.expand();

// Определяем платформу для AppRoot
const platform = WebApp.platform === 'ios' ? 'ios' : 'base';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <AppRoot
    appearance={WebApp.colorScheme}
    platform={platform}
  >
    <App />
  </AppRoot>
);
```

### Root Component

```tsx
// src/App.tsx
import { useEffect } from 'react';
import WebApp from '@twa-dev/sdk';
import { BrowserRouter, Routes, Route } from 'react-router-dom';

import { MainLayout } from './components/layouts/MainLayout';
import { HomePage } from './pages/HomePage';
import { ProfilePage } from './pages/ProfilePage';

function App() {
  useEffect(() => {
    // Настройка цвета header
    WebApp.setHeaderColor('secondary_bg_color');
    WebApp.setBackgroundColor('secondary_bg_color');
    
    // Включаем closing confirmation если есть несохранённые данные
    // WebApp.enableClosingConfirmation();
    
    return () => {
      // Cleanup
    };
  }, []);

  return (
    <BrowserRouter>
      <MainLayout>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/profile" element={<ProfilePage />} />
        </Routes>
      </MainLayout>
    </BrowserRouter>
  );
}

export default App;
```

---

## 📱 TELEGRAM SDK (@twa-dev/sdk)

### Основные объекты и методы

```typescript
// src/services/telegram.ts
import WebApp from '@twa-dev/sdk';

// ═══════════════════════════════════════════════════════════════════
// Информация о пользователе
// ═══════════════════════════════════════════════════════════════════

export function getTelegramUser() {
  const user = WebApp.initDataUnsafe.user;
  
  if (!user) {
    return null;
  }
  
  return {
    id: user.id,
    firstName: user.first_name,
    lastName: user.last_name,
    username: user.username,
    languageCode: user.language_code,
    isPremium: user.is_premium,
    photoUrl: user.photo_url,
  };
}

// ═══════════════════════════════════════════════════════════════════
// Init Data (для отправки на backend)
// ═══════════════════════════════════════════════════════════════════

export function getInitData(): string {
  return WebApp.initData; // Строка для валидации на сервере
}

export function getInitDataUnsafe() {
  return WebApp.initDataUnsafe; // Parsed объект (НЕ для авторизации!)
}

// ═══════════════════════════════════════════════════════════════════
// Платформа и тема
// ═══════════════════════════════════════════════════════════════════

export function getPlatform(): 'ios' | 'android' | 'web' | 'unknown' {
  const platform = WebApp.platform;
  
  if (platform === 'ios') return 'ios';
  if (platform === 'android' || platform === 'android_x') return 'android';
  if (platform === 'web' || platform === 'weba' || platform === 'webk') return 'web';
  
  return 'unknown';
}

export function getColorScheme(): 'light' | 'dark' {
  return WebApp.colorScheme;
}

export function getThemeParams() {
  return WebApp.themeParams;
}

// ═══════════════════════════════════════════════════════════════════
// Viewport
// ═══════════════════════════════════════════════════════════════════

export function getViewport() {
  return {
    height: WebApp.viewportHeight,
    stableHeight: WebApp.viewportStableHeight,
    isExpanded: WebApp.isExpanded,
  };
}

export function expandApp() {
  WebApp.expand();
}

// ═══════════════════════════════════════════════════════════════════
// Haptic Feedback
// ═══════════════════════════════════════════════════════════════════

export const haptic = {
  /** Лёгкая вибрация для UI элементов */
  light: () => WebApp.HapticFeedback.impactOccurred('light'),
  
  /** Средняя вибрация для подтверждений */
  medium: () => WebApp.HapticFeedback.impactOccurred('medium'),
  
  /** Сильная вибрация для важных действий */
  heavy: () => WebApp.HapticFeedback.impactOccurred('heavy'),
  
  /** Вибрация при выборе элемента */
  selection: () => WebApp.HapticFeedback.selectionChanged(),
  
  /** Уведомление об успехе */
  success: () => WebApp.HapticFeedback.notificationOccurred('success'),
  
  /** Уведомление об ошибке */
  error: () => WebApp.HapticFeedback.notificationOccurred('error'),
  
  /** Предупреждение */
  warning: () => WebApp.HapticFeedback.notificationOccurred('warning'),
};

// ═══════════════════════════════════════════════════════════════════
// Alerts и Popups
// ═══════════════════════════════════════════════════════════════════

export function showAlert(message: string): Promise<void> {
  return new Promise((resolve) => {
    WebApp.showAlert(message, resolve);
  });
}

export function showConfirm(message: string): Promise<boolean> {
  return new Promise((resolve) => {
    WebApp.showConfirm(message, resolve);
  });
}

interface PopupButton {
  id: string;
  type?: 'default' | 'ok' | 'close' | 'cancel' | 'destructive';
  text?: string;
}

export function showPopup(
  title: string,
  message: string,
  buttons: PopupButton[] = [{ id: 'ok', type: 'ok' }]
): Promise<string> {
  return new Promise((resolve) => {
    WebApp.showPopup(
      { title, message, buttons },
      (buttonId) => resolve(buttonId || '')
    );
  });
}

// ═══════════════════════════════════════════════════════════════════
// Закрытие приложения
// ═══════════════════════════════════════════════════════════════════

export function closeApp() {
  WebApp.close();
}

export function enableClosingConfirmation() {
  WebApp.enableClosingConfirmation();
}

export function disableClosingConfirmation() {
  WebApp.disableClosingConfirmation();
}

// ═══════════════════════════════════════════════════════════════════
// Ссылки
// ═══════════════════════════════════════════════════════════════════

export function openLink(url: string, options?: { try_instant_view?: boolean }) {
  WebApp.openLink(url, options);
}

export function openTelegramLink(url: string) {
  WebApp.openTelegramLink(url);
}

// ═══════════════════════════════════════════════════════════════════
// QR Scanner
// ═══════════════════════════════════════════════════════════════════

export function showQRScanner(text?: string): Promise<string | null> {
  return new Promise((resolve) => {
    WebApp.showScanQrPopup(
      { text },
      (data) => {
        WebApp.closeScanQrPopup();
        resolve(data || null);
        return true; // Закрыть после первого скана
      }
    );
  });
}

// ═══════════════════════════════════════════════════════════════════
// Cloud Storage
// ═══════════════════════════════════════════════════════════════════

export const cloudStorage = {
  async get(key: string): Promise<string | null> {
    return new Promise((resolve, reject) => {
      WebApp.CloudStorage.getItem(key, (error, value) => {
        if (error) reject(error);
        else resolve(value || null);
      });
    });
  },
  
  async set(key: string, value: string): Promise<void> {
    return new Promise((resolve, reject) => {
      WebApp.CloudStorage.setItem(key, value, (error) => {
        if (error) reject(error);
        else resolve();
      });
    });
  },
  
  async remove(key: string): Promise<void> {
    return new Promise((resolve, reject) => {
      WebApp.CloudStorage.removeItem(key, (error) => {
        if (error) reject(error);
        else resolve();
      });
    });
  },
  
  async getKeys(): Promise<string[]> {
    return new Promise((resolve, reject) => {
      WebApp.CloudStorage.getKeys((error, keys) => {
        if (error) reject(error);
        else resolve(keys || []);
      });
    });
  },
};
```

### Custom Hooks для Telegram

```tsx
// src/hooks/useTelegram.ts
import { useEffect, useState, useCallback } from 'react';
import WebApp from '@twa-dev/sdk';
import { getTelegramUser, haptic } from '../services/telegram';

export function useTelegramUser() {
  const [user] = useState(() => getTelegramUser());
  return user;
}

export function useColorScheme() {
  const [colorScheme, setColorScheme] = useState(WebApp.colorScheme);
  
  useEffect(() => {
    const handler = () => setColorScheme(WebApp.colorScheme);
    WebApp.onEvent('themeChanged', handler);
    
    return () => WebApp.offEvent('themeChanged', handler);
  }, []);
  
  return colorScheme;
}

export function useViewport() {
  const [viewport, setViewport] = useState({
    height: WebApp.viewportHeight,
    stableHeight: WebApp.viewportStableHeight,
    isExpanded: WebApp.isExpanded,
  });
  
  useEffect(() => {
    const handler = () => {
      setViewport({
        height: WebApp.viewportHeight,
        stableHeight: WebApp.viewportStableHeight,
        isExpanded: WebApp.isExpanded,
      });
    };
    
    WebApp.onEvent('viewportChanged', handler);
    return () => WebApp.offEvent('viewportChanged', handler);
  }, []);
  
  return viewport;
}

export function useHaptic() {
  return haptic;
}
```

### Main Button Hook

```tsx
// src/hooks/useMainButton.ts
import { useEffect, useCallback } from 'react';
import WebApp from '@twa-dev/sdk';
import { haptic } from '../services/telegram';

interface MainButtonOptions {
  text: string;
  onClick: () => void | Promise<void>;
  color?: string;
  textColor?: string;
  isVisible?: boolean;
  isActive?: boolean;
  isProgressVisible?: boolean;
}

export function useMainButton(options: MainButtonOptions) {
  const {
    text,
    onClick,
    color,
    textColor,
    isVisible = true,
    isActive = true,
    isProgressVisible = false,
  } = options;

  const handleClick = useCallback(async () => {
    haptic.medium();
    await onClick();
  }, [onClick]);

  useEffect(() => {
    const MainButton = WebApp.MainButton;
    
    // Настройка кнопки
    MainButton.setText(text);
    
    if (color) MainButton.color = color;
    if (textColor) MainButton.textColor = textColor;
    
    // Обработчик клика
    MainButton.onClick(handleClick);
    
    // Видимость и состояние
    if (isVisible) {
      MainButton.show();
    } else {
      MainButton.hide();
    }
    
    if (isActive) {
      MainButton.enable();
    } else {
      MainButton.disable();
    }
    
    if (isProgressVisible) {
      MainButton.showProgress();
    } else {
      MainButton.hideProgress();
    }
    
    return () => {
      MainButton.offClick(handleClick);
      MainButton.hide();
    };
  }, [text, color, textColor, isVisible, isActive, isProgressVisible, handleClick]);

  // Методы для управления
  return {
    show: () => WebApp.MainButton.show(),
    hide: () => WebApp.MainButton.hide(),
    enable: () => WebApp.MainButton.enable(),
    disable: () => WebApp.MainButton.disable(),
    showProgress: () => WebApp.MainButton.showProgress(),
    hideProgress: () => WebApp.MainButton.hideProgress(),
    setText: (text: string) => WebApp.MainButton.setText(text),
  };
}
```

### Back Button Hook

```tsx
// src/hooks/useBackButton.ts
import { useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import WebApp from '@twa-dev/sdk';
import { haptic } from '../services/telegram';

interface BackButtonOptions {
  onClick?: () => void;
  isVisible?: boolean;
}

export function useBackButton(options: BackButtonOptions = {}) {
  const navigate = useNavigate();
  const { onClick, isVisible = true } = options;

  const handleClick = useCallback(() => {
    haptic.light();
    
    if (onClick) {
      onClick();
    } else {
      navigate(-1);
    }
  }, [onClick, navigate]);

  useEffect(() => {
    const BackButton = WebApp.BackButton;
    
    if (isVisible) {
      BackButton.show();
      BackButton.onClick(handleClick);
    } else {
      BackButton.hide();
    }
    
    return () => {
      BackButton.offClick(handleClick);
      BackButton.hide();
    };
  }, [isVisible, handleClick]);

  return {
    show: () => WebApp.BackButton.show(),
    hide: () => WebApp.BackButton.hide(),
  };
}
```

---

## 🎨 UI КОМПОНЕНТЫ (@telegram-apps/telegram-ui)

### Обязательная обёртка AppRoot

```tsx
// AppRoot ОБЯЗАТЕЛЕН для всех компонентов telegram-ui
import { AppRoot } from '@telegram-apps/telegram-ui';
import '@telegram-apps/telegram-ui/dist/styles.css';

// В main.tsx или App.tsx
<AppRoot
  appearance="dark"        // 'light' | 'dark'
  platform="ios"           // 'ios' | 'base'
>
  {/* Все компоненты здесь */}
</AppRoot>
```

### Основные компоненты

```tsx
// src/components/examples/ComponentsShowcase.tsx
import {
  // Layout
  AppRoot,
  Section,
  List,
  
  // Navigation
  Tabbar,
  
  // Blocks
  Cell,
  Info,
  Badge,
  Avatar,
  Placeholder,
  
  // Forms
  Input,
  Textarea,
  Checkbox,
  Radio,
  Switch,
  Slider,
  Select,
  
  // Buttons
  Button,
  IconButton,
  
  // Feedback
  Spinner,
  Progress,
  Skeleton,
  
  // Overlays
  Modal,
  Snackbar,
  
  // Typography
  Title,
  Headline,
  Text,
  Subheadline,
  Caption,
  LargeTitle,
} from '@telegram-apps/telegram-ui';


// ═══════════════════════════════════════════════════════════════════
// Section + List + Cell — основной паттерн
// ═══════════════════════════════════════════════════════════════════

function SettingsExample() {
  return (
    <List>
      <Section header="Настройки аккаунта">
        <Cell
          before={<Avatar size={48} src="/avatar.jpg" />}
          subtitle="@username"
          after={<Badge type="number">3</Badge>}
        >
          Иван Иванов
        </Cell>
      </Section>
      
      <Section header="Уведомления">
        <Cell
          after={<Switch defaultChecked />}
          description="Получать push-уведомления"
        >
          Уведомления
        </Cell>
        
        <Cell
          after={<Switch />}
          description="Звук при получении сообщения"
        >
          Звуки
        </Cell>
      </Section>
      
      <Section header="О приложении">
        <Cell after={<Text>1.0.0</Text>}>
          Версия
        </Cell>
      </Section>
    </List>
  );
}


// ═══════════════════════════════════════════════════════════════════
// Формы
// ═══════════════════════════════════════════════════════════════════

function FormExample() {
  const [name, setName] = useState('');
  
  return (
    <List>
      <Section header="Контактная информация">
        <Input
          header="Имя"
          placeholder="Введите имя"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        
        <Input
          header="Email"
          type="email"
          placeholder="example@mail.com"
        />
        
        <Textarea
          header="Комментарий"
          placeholder="Напишите что-нибудь..."
          rows={4}
        />
      </Section>
      
      <Section header="Предпочтения">
        <Cell after={<Checkbox defaultChecked />}>
          Принимаю условия
        </Cell>
        
        <Cell after={<Radio name="plan" value="free" />}>
          Бесплатный план
        </Cell>
        
        <Cell after={<Radio name="plan" value="premium" defaultChecked />}>
          Премиум план
        </Cell>
      </Section>
      
      <Section>
        <Cell>
          <Button size="l" stretched>
            Отправить
          </Button>
        </Cell>
      </Section>
    </List>
  );
}


// ═══════════════════════════════════════════════════════════════════
// Placeholder — пустые состояния
// ═══════════════════════════════════════════════════════════════════

function EmptyState() {
  return (
    <Placeholder
      header="Пока ничего нет"
      description="Здесь будут отображаться ваши заказы"
      action={<Button size="l">Создать заказ</Button>}
    >
      <img
        src="/empty-illustration.png"
        alt="Empty"
        style={{ width: 144, height: 144 }}
      />
    </Placeholder>
  );
}


// ═══════════════════════════════════════════════════════════════════
// Modal
// ═══════════════════════════════════════════════════════════════════

function ModalExample() {
  const [isOpen, setIsOpen] = useState(false);
  
  return (
    <>
      <Button onClick={() => setIsOpen(true)}>
        Открыть модалку
      </Button>
      
      <Modal
        open={isOpen}
        onOpenChange={setIsOpen}
        header={<Modal.Header>Заголовок</Modal.Header>}
      >
        <Placeholder
          description="Содержимое модального окна"
          action={
            <Button size="l" stretched onClick={() => setIsOpen(false)}>
              Закрыть
            </Button>
          }
        />
      </Modal>
    </>
  );
}


// ═══════════════════════════════════════════════════════════════════
// Tabbar — нижняя навигация
// ═══════════════════════════════════════════════════════════════════

function TabbarExample() {
  const [activeTab, setActiveTab] = useState('home');
  
  return (
    <Tabbar>
      <Tabbar.Item
        text="Главная"
        selected={activeTab === 'home'}
        onClick={() => setActiveTab('home')}
      >
        <HomeIcon />
      </Tabbar.Item>
      
      <Tabbar.Item
        text="Профиль"
        selected={activeTab === 'profile'}
        onClick={() => setActiveTab('profile')}
      >
        <UserIcon />
      </Tabbar.Item>
      
      <Tabbar.Item
        text="Настройки"
        selected={activeTab === 'settings'}
        onClick={() => setActiveTab('settings')}
      >
        <SettingsIcon />
      </Tabbar.Item>
    </Tabbar>
  );
}
```

### Адаптация под платформы

```tsx
// src/components/layouts/MainLayout.tsx
import { ReactNode } from 'react';
import WebApp from '@twa-dev/sdk';
import { List } from '@telegram-apps/telegram-ui';

interface MainLayoutProps {
  children: ReactNode;
}

export function MainLayout({ children }: MainLayoutProps) {
  const platform = WebApp.platform;
  const isIOS = platform === 'ios';
  
  return (
    <div
      style={{
        // Safe area для iOS
        paddingTop: isIOS ? 'env(safe-area-inset-top)' : 0,
        paddingBottom: isIOS ? 'env(safe-area-inset-bottom)' : 0,
        minHeight: '100vh',
      }}
    >
      <List>{children}</List>
    </div>
  );
}
```

---

## 🔐 ВАЛИДАЦИЯ INIT DATA (BACKEND)

### Python (FastAPI)

```python
# backend/validate_init_data.py
import hashlib
import hmac
import json
from urllib.parse import parse_qs, unquote
from typing import Optional
from datetime import datetime, timedelta

from fastapi import HTTPException, Header, Depends
from pydantic import BaseModel


class TelegramUser(BaseModel):
    id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    language_code: Optional[str] = None
    is_premium: Optional[bool] = None
    photo_url: Optional[str] = None


class InitData(BaseModel):
    query_id: Optional[str] = None
    user: Optional[TelegramUser] = None
    auth_date: int
    hash: str


def validate_init_data(
    init_data: str,
    bot_token: str,
    max_age_seconds: int = 86400,  # 24 часа
) -> InitData:
    """
    Валидация initData от Telegram Mini App.
    
    Raises:
        ValueError: если данные невалидны или устарели
    """
    # Парсим строку
    parsed = parse_qs(init_data)
    
    # Извлекаем hash
    received_hash = parsed.get('hash', [None])[0]
    if not received_hash:
        raise ValueError("Missing hash")
    
    # Собираем данные для проверки (без hash, отсортированные)
    data_check_arr = []
    for key, values in sorted(parsed.items()):
        if key != 'hash':
            data_check_arr.append(f"{key}={values[0]}")
    
    data_check_string = '\n'.join(data_check_arr)
    
    # Создаём secret key
    secret_key = hmac.new(
        b'WebAppData',
        bot_token.encode(),
        hashlib.sha256
    ).digest()
    
    # Вычисляем hash
    calculated_hash = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256
    ).hexdigest()
    
    # Сравниваем
    if not hmac.compare_digest(calculated_hash, received_hash):
        raise ValueError("Invalid hash")
    
    # Проверяем auth_date
    auth_date = int(parsed.get('auth_date', [0])[0])
    current_time = int(datetime.now().timestamp())
    
    if current_time - auth_date > max_age_seconds:
        raise ValueError("Init data expired")
    
    # Парсим user
    user_data = parsed.get('user', [None])[0]
    user = None
    if user_data:
        user = TelegramUser(**json.loads(unquote(user_data)))
    
    return InitData(
        query_id=parsed.get('query_id', [None])[0],
        user=user,
        auth_date=auth_date,
        hash=received_hash,
    )


# FastAPI Dependency
async def get_telegram_user(
    x_init_data: str = Header(..., alias="X-Init-Data"),
) -> TelegramUser:
    """Dependency для получения валидированного пользователя."""
    import os
    
    bot_token = os.environ["BOT_TOKEN"]
    
    try:
        init_data = validate_init_data(x_init_data, bot_token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    
    if not init_data.user:
        raise HTTPException(status_code=401, detail="User data missing")
    
    return init_data.user


# Пример использования в endpoint
from fastapi import FastAPI

app = FastAPI()

@app.get("/api/profile")
async def get_profile(user: TelegramUser = Depends(get_telegram_user)):
    return {
        "id": user.id,
        "name": user.first_name,
        "username": user.username,
    }
```

### TypeScript (Express.js)

```typescript
// backend/validate-init-data.ts
import crypto from 'crypto';
import { Request, Response, NextFunction } from 'express';

interface TelegramUser {
  id: number;
  first_name: string;
  last_name?: string;
  username?: string;
  language_code?: string;
  is_premium?: boolean;
  photo_url?: string;
}

interface InitData {
  query_id?: string;
  user?: TelegramUser;
  auth_date: number;
  hash: string;
}

export function validateInitData(
  initData: string,
  botToken: string,
  maxAgeSeconds: number = 86400
): InitData {
  const params = new URLSearchParams(initData);
  
  const hash = params.get('hash');
  if (!hash) {
    throw new Error('Missing hash');
  }
  
  // Собираем строку для проверки
  const dataCheckArr: string[] = [];
  params.forEach((value, key) => {
    if (key !== 'hash') {
      dataCheckArr.push(`${key}=${value}`);
    }
  });
  dataCheckArr.sort();
  
  const dataCheckString = dataCheckArr.join('\n');
  
  // Создаём secret key
  const secretKey = crypto
    .createHmac('sha256', 'WebAppData')
    .update(botToken)
    .digest();
  
  // Вычисляем hash
  const calculatedHash = crypto
    .createHmac('sha256', secretKey)
    .update(dataCheckString)
    .digest('hex');
  
  // Сравниваем
  if (!crypto.timingSafeEqual(
    Buffer.from(calculatedHash),
    Buffer.from(hash)
  )) {
    throw new Error('Invalid hash');
  }
  
  // Проверяем auth_date
  const authDate = parseInt(params.get('auth_date') || '0', 10);
  const currentTime = Math.floor(Date.now() / 1000);
  
  if (currentTime - authDate > maxAgeSeconds) {
    throw new Error('Init data expired');
  }
  
  // Парсим user
  const userStr = params.get('user');
  const user = userStr ? JSON.parse(decodeURIComponent(userStr)) : undefined;
  
  return {
    query_id: params.get('query_id') || undefined,
    user,
    auth_date: authDate,
    hash,
  };
}

// Express middleware
export function telegramAuthMiddleware(
  req: Request,
  res: Response,
  next: NextFunction
) {
  const initData = req.headers['x-init-data'] as string;
  
  if (!initData) {
    return res.status(401).json({ error: 'Missing init data' });
  }
  
  try {
    const botToken = process.env.BOT_TOKEN!;
    const data = validateInitData(initData, botToken);
    
    if (!data.user) {
      return res.status(401).json({ error: 'User data missing' });
    }
    
    // Добавляем user в request
    (req as any).telegramUser = data.user;
    next();
  } catch (error) {
    return res.status(401).json({ error: (error as Error).message });
  }
}
```

### Отправка initData с Frontend

```typescript
// src/services/api.ts
import WebApp from '@twa-dev/sdk';

const API_URL = import.meta.env.VITE_API_URL || '/api';

async function fetchWithAuth<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const response = await fetch(`${API_URL}${endpoint}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-Init-Data': WebApp.initData, // Отправляем initData
      ...options.headers,
    },
  });
  
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }
  
  return response.json();
}

// Использование
export const api = {
  getProfile: () => fetchWithAuth<UserProfile>('/profile'),
  
  updateProfile: (data: UpdateProfileData) =>
    fetchWithAuth<UserProfile>('/profile', {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  
  createOrder: (data: CreateOrderData) =>
    fetchWithAuth<Order>('/orders', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
};
```

---

## 📦 ZUSTAND STORE

```typescript
// src/stores/appStore.ts
import { create } from 'zustand';
import { devtools, persist } from 'zustand/middleware';
import WebApp from '@twa-dev/sdk';
import { getTelegramUser } from '../services/telegram';

interface TelegramUser {
  id: number;
  firstName: string;
  lastName?: string;
  username?: string;
  isPremium?: boolean;
}

interface AppState {
  // User
  user: TelegramUser | null;
  isLoading: boolean;
  
  // Theme
  colorScheme: 'light' | 'dark';
  
  // Actions
  initApp: () => void;
  setLoading: (loading: boolean) => void;
}

export const useAppStore = create<AppState>()(
  devtools(
    (set) => ({
      user: null,
      isLoading: true,
      colorScheme: WebApp.colorScheme,
      
      initApp: () => {
        const user = getTelegramUser();
        set({ user, isLoading: false });
      },
      
      setLoading: (isLoading) => set({ isLoading }),
    }),
    { name: 'app-store' }
  )
);

// Селекторы
export const useUser = () => useAppStore((state) => state.user);
export const useIsLoading = () => useAppStore((state) => state.isLoading);
```

---

## ✅ ЧЕКЛИСТ ПЕРЕД ДЕПЛОЕМ

```
ИНИЦИАЛИЗАЦИЯ
□ WebApp.ready() вызван в main.tsx
□ AppRoot оборачивает всё приложение
□ Стили @telegram-apps/telegram-ui подключены
□ Определена платформа для AppRoot

БЕЗОПАСНОСТЬ
□ initData валидируется на backend
□ Нет чувствительных данных в localStorage
□ HTTPS для production

UX
□ Haptic feedback на всех интерактивных элементах
□ MainButton для основных действий
□ BackButton для навигации
□ Safe area учтена для iOS
□ Адаптация под colorScheme (light/dark)
□ Загрузочные состояния (Spinner, Skeleton)

ПРОИЗВОДИТЕЛЬНОСТЬ
□ Минимум re-renders (Zustand селекторы)
□ Lazy loading для тяжёлых компонентов
□ Оптимизированные изображения
□ Bundle size проверен

ДЕПЛОЙ
□ HTTPS сертификат
□ Правильный base в vite.config
□ Переменные окружения настроены
□ Bot настроен в @BotFather
```

---

## 🚀 БЫСТРЫЙ ПРОМПТ ДЛЯ CLAUDE CODE

```
Telegram Mini App на React + TypeScript. Используй:
- @twa-dev/sdk для Telegram API
- @telegram-apps/telegram-ui для UI компонентов
- Zustand для state management

ОБЯЗАТЕЛЬНО:
✅ WebApp.ready() в main.tsx
✅ AppRoot для telegram-ui компонентов
✅ Haptic feedback (haptic.light/medium/success)
✅ useMainButton и useBackButton hooks
✅ Валидация initData на backend
✅ Safe area insets для iOS

КОМПОНЕНТЫ telegram-ui:
- Section + Cell для списков
- Input/Textarea для форм
- Button с size="l" stretched
- Placeholder для пустых состояний
- Modal для попапов
- Spinner/Skeleton для загрузки

ЗАПРЕЩЕНО:
❌ Хардкод цветов (используй themeParams)
❌ Доверять initDataUnsafe без валидации
❌ Игнорировать platform (ios/android/web)
❌ Забывать про haptic feedback
```

---

**Версия:** 1.0  
**Дата:** 01.12.2025  
**Референс:** Telegram Mini Apps docs, @twa-dev/sdk 8.x, @telegram-apps/telegram-ui 2.x
