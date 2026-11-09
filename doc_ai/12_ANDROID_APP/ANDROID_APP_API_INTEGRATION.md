# ANDROID_APP_API_INTEGRATION.md
# Интеграция Android-приложения с backend и узлами

**Сверено с кодом:** 2026-11-07.

Документ описывает, как Android-приложение общается с системой:

- с backend (Laravel);
- косвенно — с узлами ESP32 через режим provisioning.


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: обратная совместимость со старыми форматами и алиасами не поддерживается.

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
- `POST /api/zones/{id}/commands` — команды на зону (route role: operator/admin/agronomist/engineer)
- `POST /api/nodes/{id}/commands` — локальные команды на узел (калибровка и т.п.)

**Алерты:**
- `GET /api/alerts` — список алертов (опционально `?zone_id={id}&status={ACTIVE|RESOLVED}`)
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

Ошибки (контракт фазы 2/3, совпадает с Laravel API и Vue):

```json
{
  "status": "error",
  "code": "zone_not_ready",
  "message": "Зона не готова к запуску цикла",
  "human_error_message": "Зона не готова к запуску цикла",
  "title": "Зона не готова"
}
```

**Локализация в приложении:**

- Каталоги `error_codes.json` и `alert_codes.json` копируются в `app/src/main/assets/i18n/` при `make i18n-catalog-fix` / `sync_i18n_catalogs.py`.
- `ApiErrorParser` читает `human_error_message` из ответа; при отсутствии — lookup в `ErrorCatalog` по `code` (snake_case).
- Сырые English-сообщения **не показываются** оператору (fallback — общий русский текст).
- Тексты алертов в списке локализуются через `AlertCatalog` по полю `code` из API.

Аутентификация: передача токена в заголовке `Authorization: Bearer <token>`.

### 1.2. Обновление данных

Активные operator ViewModel выполняют REST polling:

- `OverviewViewModel` — обзор теплиц каждые 10 s;
- `ZoneListViewModel`, `ZoneOperatorViewModel`, `NodeOperatorViewModel` — каждые 8 s;
- `OperatorAlertsViewModel` — ACTIVE alerts каждые 5 s.

Источник — `features/operator/ListViewModels.kt` и `DetailViewModels.kt`. Это задержки цикла; фактическое время запросов зависит от сети.

`RealtimeService.connectWebSocket` строит URL `/ws/{channel}`, которого нет в Laravel/Reverb. В классе отсутствуют Pusher subscribe/private-channel auth, а активные operator ViewModel его не вызывают. Автоматический переход WS → polling не реализован; наличие OkHttp WebSocket не означает рабочую Reverb-интеграцию.

### 1.3. Состояние UI и Room

Основной путь — Compose → operator ViewModel → `OperatorRepository` → Retrofit APIs; результат хранится в `StateFlow` в памяти. Ошибка запроса показывается в UI, отдельные ViewModel могут сохранить предыдущий список в памяти.

Room entities/DAOs и старые repository/use-case цепочки существуют для Greenhouses/Zones/Nodes/Telemetry/Alerts, но не являются универсальным источником текущих operator screens. `TelemetryDao.getHistory(limit=1000)` ограничивает результат SELECT, а не размер базы. Гарантированного offline-кэша всех экранов и синхронизации offline-команд нет.

---

## 2. Режим provisioning узлов (первая настройка)

**Статус на 2026-11-06: Android provisioning — scaffold, сквозная настройка
несовместима с текущим ESP32 setup portal.** Не выдавать её за рабочую функцию.
`ProvisioningRepository.kt` отправляет `/api/provision` с `wifi_ssid`,
`wifi_password`, `backend_base_url`; в текущей прошивке такого маршрута нет.

### 2.1. Текущий рабочий путь через браузер

1. Подключитесь к AP узла (`HYDRO-NODE-*` / `HYDRO-SETUP`, по конфигурации устройства).
2. Откройте `http://192.168.4.1/` и заполните форму сети и MQTT.
3. Portal отправляет `POST /wifi/connect` с полями `ssid`, `password`,
   `mqtt_host`, `mqtt_port`. Сейчас `mqtt_host` принимает IPv4; hostname не поддержан.
4. После успешной валидации узел сохраняет NodeConfig в NVS и перезагружается.
   Регистрация идёт через `hydro/node_hello`; затем проверяются lifecycle/bind и
   `config_report` по их контрактам. Успешный POST не равен готовности узла к командам.

Пример формы запроса (значения условные, не credentials стенда):

```json
{
  "ssid": "example-network",
  "password": "example-password",
  "mqtt_host": "192.168.1.10",
  "mqtt_port": 1883
}
```

Канон: [WIFI_PROVISIONING_FIRST_RUN.md](../02_HARDWARE_FIRMWARE/WIFI_PROVISIONING_FIRST_RUN.md).
Код portal: `firmware/nodes/common/components/setup_portal/setup_portal.c`.

### 2.2. Что требуется для завершения Android provisioning

Клиент должен согласовать endpoint и поля с portal, передавать MQTT host/port,
обрабатывать ошибки валидации и отдельно проверять появление/готовность ноды.
Одна замена URL несовместимость не устраняет. `hydro/system/announce/*` — planned,
а не действующий канал регистрации. До проверки интеграции используйте путь через браузер.

### 2.3. Требуемые разрешения

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
│   ├── operator/        # Активные operator ViewModel и REST repository
│   └── provisioning/    # Scaffold настройки узлов
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

1. `OperatorScreens` подписываются на `StateFlow` своих operator ViewModel.
2. ViewModel вызывает `OperatorRepository`; repository выполняет REST-запросы.
3. ViewModel обновляет in-memory state; периодический цикл повторяет refresh.
4. Login и Settings используют отдельные auth/settings ViewModel и DataStore для token/server preferences.

Room-цепочки нужно проверять по конкретному consumer; они не подменяют этот активный путь.

---

## 4. Конфигурация окружений

### 4.1. Product Flavors

Приложение поддерживает три окружения через Gradle flavors:

- **dev** — `applicationIdSuffix = ".dev"`, конфиг из `env.dev.json`
- **staging** — `applicationIdSuffix = ".staging"`, конфиг из `env.staging.json`
- **prod** — без суффикса, конфиг из `env.prod.json`

### 4.2. Конфигурационные файлы

Шаблоны окружений находятся в `mobile/configs/`; копии для `ConfigLoader` — в `app/src/main/assets/configs/`:
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

Gradle выбирает имя assets-файла через `ENV_CONFIG_FILE`; автоматической задачи синхронизации `mobile/configs/` в `app/build.gradle.kts` нет. Активные Retrofit-запросы используют `ServerEndpointStore` и `DynamicBaseUrlInterceptor`: сервер меняется на экране Settings и хранится в preferences. `ConfigLoader` остаётся для отдельных consumers, включая WebSocket-заготовку; изменение одного JSON не заменяет выбранный оператором endpoint. Для эмулятора default — `10.0.2.2:8080`; `localhost` на телефоне указывает на сам телефон.

---

## 5. UX-паттерны в Android

Подключённые экраны и действия — [ANDROID_APP_SCREENS.md](ANDROID_APP_SCREENS.md).

- Login получает token; `NetworkModule` добавляет его как Bearer.
- Settings задаёт хост, порт и HTTPS.
- Operator screens показывают последние данные, control mode и stage; history charts и редактор grow-cycle в них не подключены.
- Список алертов показывает ACTIVE. `PATCH /api/alerts/{id}/ack` пишет `acknowledged_at` и не переводит статус в RESOLVED: подтверждённый safety-алерт остаётся активным и блокирующим. Отдельного статуса `acknowledged` нет. Ручное закрытие — `PATCH /api/alerts/{id}/resolve`; для safety-кодов при активном условии API отвечает `409`.
- Provisioning экран существует как scaffold; его несовместимость с firmware описана в §2.

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
4. **Учитывать текущий путь данных** — operator screens используют REST и in-memory StateFlow; offline/Room поведение проверяется отдельно по consumer
5. **Обработка ошибок** — показывать понятные сообщения пользователю при ошибках сети
6. **Любые изменения протокола provisioning** отражать в этом документе и на стороне прошивки узла

Android-приложение — это прежде всего **клиент backend-API** и удобный инструмент настройки узлов, а не прямой «контроллер» оборудования.

---

## 8. Границы реализации

History Canvas, Room DAOs и OkHttp WebSocket присутствуют как отдельные компоненты, но не подтверждают подключение этих сценариев в operator UI. Текущие границы — [ANDROID_APP_ARCH.md](ANDROID_APP_ARCH.md); фактический grow-cycle coverage — [ANDROID_GROW_CYCLE_UI.md](ANDROID_GROW_CYCLE_UI.md).
