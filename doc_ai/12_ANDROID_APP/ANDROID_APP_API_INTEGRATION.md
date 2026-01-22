# ANDROID_APP_API_INTEGRATION.md
# Интеграция Android-приложения с backend и узлами

Документ описывает, как Android-приложение общается с системой:

- с backend (Laravel);
- косвенно — с узлами ESP32 через режим provisioning.


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: legacy форматы/алиасы удалены, обратная совместимость не поддерживается.

---

## 1. Взаимодействие с backend

### 1.1. REST API

Android использует те же REST-эндпоинты, что и веб-frontend, через `/api/*`:

**Аутентификация:**
- `POST /api/auth/login` — авторизация, возвращает `{status: "ok", data: {token: "...", user: {...}}}`

**Теплицы и зоны:**
- `GET /api/greenhouses` — список теплиц
- `GET /api/greenhouses/{id}` — детали теплицы
- `GET /api/zones` — список зон (опционально `?greenhouse_id={id}`)
- `GET /api/zones/{id}` — детали зоны

**Телеметрия:**
- `GET /api/zones/{id}/telemetry/last` — последние значения по зоне
- `GET /api/zones/{id}/telemetry/history?metric={PH|EC|TEMPERATURE|...}&from={ISO8601}&to={ISO8601}` — история для графиков

**Команды:**
- `POST /api/zones/{id}/commands` — команды на зону (требует роль operator/admin)
- `POST /api/nodes/{id}/commands` — локальные команды на узел (калибровка и т.п.)

**Алерты:**
- `GET /api/alerts` — список алертов (опционально `?zone_id={id}&status={open|acknowledged}`)
- `GET /api/alerts/{id}` — детали алерта
- `PATCH /api/alerts/{id}/ack` — подтверждение алерта

**Формат ответов:**
Все ответы используют стандартный формат:
```json
{
  "status": "ok",
  "data": { ... }
}
```

Ошибки:
```json
{
  "status": "error",
  "message": "Error description",
  "code": 400
}
```

Аутентификация: передача токена в заголовке `Authorization: Bearer <token>`.

### 1.2. Realtime обновления

Реализованы два механизма:

1. **Polling (текущая реализация)** — периодические запросы к REST API для обновления данных:
   - Теплицы/зоны: каждые 10 секунд
   - Алерты: каждые 5 секунд
   - Телеметрия: по запросу пользователя

2. **WebSocket (подготовлено)** — `RealtimeService` поддерживает подключение к WebSocket каналам:
   - Подключение к `wss://{backend}/ws/{channel}`
   - Автоматическое переподключение при разрыве
   - Fallback на polling при недоступности WebSocket

### 1.3. Кэширование данных

Используется **Room Database** для локального кэширования:
- **Greenhouses** — кэш списка теплиц
- **Zones** — кэш зон с привязкой к теплицам
- **Nodes** — кэш узлов с привязкой к зонам
- **Telemetry** — кэш истории телеметрии (до 1000 точек на метрику)
- **Alerts** — кэш алертов с фильтрацией по статусу и зоне

Стратегия кэширования:
- При первом запуске загружаются данные из API и сохраняются в Room
- UI отображает данные из Room (Flow из DAO)
- Фоновое обновление через polling обновляет кэш
- При отсутствии сети показываются кэшированные данные

---

## 2. Режим provisioning узлов (первая настройка)

Android-приложение используется для первичной настройки узлов ESP32:

### 2.1. Процесс настройки

1. **Сканирование устройств:**
   - Приложение сканирует Wi-Fi сети с префиксом `HYDRO-NODE-*` или `HYDRO-SETUP`
   - Используется `WifiManager.scanResults` для поиска доступных узлов
   - Требуется разрешение `ACCESS_FINE_LOCATION` (Android 6.0+)

2. **Подключение к узлу:**
   - Пользователь выбирает найденный узел из списка
   - Приложение подключается к Wi-Fi сети узла (режим AP)
   - По умолчанию используется IP `192.168.4.1` (стандартный для ESP32 AP mode)

3. **Отправка конфигурации:**
   - Приложение отправляет POST запрос на `http://192.168.4.1/api/provision` с JSON:
   ```json
   {
     "wifi_ssid": "SSID основной сети",
     "wifi_password": "пароль Wi-Fi",
     "backend_base_url": "https://your-backend",
     "gh_uid": "gh-main",  // опционально
     "zone_uid": "zone-a",  // опционально
     "node_name": "Имя узла"
   }
   ```

4. **Завершение:**
   - Узел сохраняет настройки в NVS и перезагружается
   - После успешного подключения к Wi-Fi и MQTT узел сообщает о себе через `hydro/system/announce/{node_uid}`
   - Приложение показывает сообщение об успехе

### 2.2. Требуемые разрешения

В `AndroidManifest.xml`:
```xml
<uses-permission android:name="android.permission.ACCESS_WIFI_STATE" />
<uses-permission android:name="android.permission.CHANGE_WIFI_STATE" />
<uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />
<uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION" />
```

---

## 3. Архитектура приложения

### 3.1. Структура пакетов

```
com.hydro.app/
├── core/
│   ├── config/          # ConfigLoader для загрузки конфигов из assets
│   ├── data/            # API интерфейсы и репозитории
│   ├── database/        # Room entities, DAOs, Database
│   ├── di/              # Hilt модули (Network, Database, APIs)
│   ├── domain/          # Domain models и DTO
│   ├── network/         # ApiResponse, TokenProvider
│   ├── prefs/           # DataStore для токена и настроек
│   └── realtime/        # RealtimeService (polling/WebSocket)
├── features/
│   ├── auth/            # Авторизация
│   ├── greenhouses/     # Список теплиц
│   ├── zones/           # Список зон и детали зоны
│   ├── alerts/          # Алерты с acknowledge
│   └── provisioning/    # Мастер настройки узлов
└── ui/
    └── screens/         # Compose экраны
```

### 3.2. Dependency Injection

Используется **Hilt** для DI:
- `NetworkModule` — Retrofit, OkHttp, Moshi
- `DatabaseModule` — Room Database
- `BackendApisModule` — API интерфейсы
- `AppModule` — ConfigLoader, PreferencesDataSource

### 3.3. Data Flow

1. **ViewModel** запрашивает данные через **Repository**
2. **Repository** проверяет кэш в **Room**, возвращает Flow
3. Фоновое обновление через **RealtimeService** (polling) обновляет кэш
4. UI автоматически обновляется через Compose StateFlow

---

## 4. Конфигурация окружений

### 4.1. Product Flavors

Приложение поддерживает три окружения через Gradle flavors:

- **dev** — `applicationIdSuffix = ".dev"`, конфиг из `env.dev.json`
- **staging** — `applicationIdSuffix = ".staging"`, конфиг из `env.staging.json`
- **prod** — без суффикса, конфиг из `env.prod.json`

### 4.2. Конфигурационные файлы

Файлы конфигурации находятся в `mobile/configs/`:
- `env.dev.json` — для разработки
- `env.staging.json` — для staging
- `env.prod.json` — для production

Формат:
```json
{
  "API_BASE_URL": "http://localhost:8080",
  "ENV": "DEV"
}
```

Конфиги копируются в `app/src/main/assets/configs/` при сборке и загружаются через `ConfigLoader`.

---

## 5. UX-паттерны в Android

Основные экраны (см. `ANDROID_APP_SCREENS.md`):

### 5.1. Авторизация
- Экран входа с полями email/password
- Токен сохраняется в DataStore
- Автоматический переход к списку теплиц после успешного входа

### 5.2. Список теплиц
- Карточки теплиц с названием, расположением, количеством зон
- Индикатор статуса (OK/WARNING/ALERT)
- FAB для алертов и provisioning

### 5.3. Список зон
- Фильтрация по теплице
- Карточки зон с названием, культурой, статусом
- Переход к детальной странице зоны

### 5.4. Детальная страница зоны
- Текущие значения телеметрии (pH, EC, температура, влажность)
- Графики истории (выбор метрики: PH, EC, TEMPERATURE, HUMIDITY_AIR)
- Команды (запуск полива и т.п.)
- Автоматическое обновление телеметрии

### 5.5. Алерты
- Список алертов с фильтрацией (все/открытые/подтвержденные)
- Индикатор уровня (critical/warning/info)
- Кнопка подтверждения (acknowledge)
- Автоматическое обновление каждые 5 секунд

### 5.6. Provisioning мастер
- Сканирование доступных узлов
- Выбор узла из списка
- Форма ввода: SSID Wi-Fi, пароль, имя узла
- Отправка конфигурации на узел
- Сообщение об успехе/ошибке

---

## 6. Технические детали

### 6.1. Сетевой стек

- **Retrofit 2.11.0** — HTTP клиент
- **Moshi 1.15.1** — JSON парсинг с Kotlin support
- **OkHttp 4.12.0** — HTTP клиент с interceptors
- **HttpLoggingInterceptor** — логирование запросов (только в debug)

### 6.2. Локальное хранилище

- **Room 2.6.1** — локальная база данных для кэширования
- **DataStore Preferences 1.1.1** — хранение токена и настроек
- **Gson 2.10.1** — парсинг конфигов и конвертеры Room

### 6.3. UI Framework

- **Jetpack Compose** — современный UI toolkit
- **Material 3** — дизайн система
- **Navigation Compose** — навигация между экранами
- **Hilt Navigation Compose** — интеграция Hilt с Navigation

### 6.4. Асинхронность

- **Kotlin Coroutines** — для асинхронных операций
- **Flow** — реактивные потоки данных из Room
- **StateFlow** — состояние в ViewModels

---

## 7. Правила для ИИ-агентов

1. **Не хардкодить URL-адреса backend-сервера** — они должны быть настраиваемыми через конфиги
2. **Следить за форматом API-запросов** — соответствие backend-документации (`../04_BACKEND_CORE/API_SPEC_FRONTEND_BACKEND_FULL.md`, `../04_BACKEND_CORE/REST_API_REFERENCE.md`)
3. **Использовать формат ответов `status/data`** — все API ответы обернуты в `ApiResponse<T>`
4. **Кэширование через Room** — все данные должны кэшироваться локально для работы offline
5. **Обработка ошибок** — показывать понятные сообщения пользователю при ошибках сети
6. **Любые изменения протокола provisioning** отражать в этом документе и на стороне прошивки узла

Android-приложение — это прежде всего **клиент backend-API** и удобный инструмент настройки узлов, а не прямой «контроллер» оборудования.

---

## 8. Известные ограничения

1. **Графики телеметрии** — текущая реализация использует простой Canvas. Для production рекомендуется использовать специализированную библиотеку (например, `vico` или `compose-charts`).

2. **WebSocket** — реализован базовый функционал, но в текущей версии используется только polling. WebSocket можно активировать при необходимости.

3. **Wi-Fi сканирование** — требует разрешения на местоположение (Android 6.0+). Пользователь должен предоставить разрешение вручную.

4. **Offline режим** — приложение показывает кэшированные данные при отсутствии сети, но не поддерживает полный offline режим с синхронизацией изменений.
