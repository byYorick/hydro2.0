# WebSocket Architecture

Архитектура WebSocket системы для real-time обновлений в приложении.

## Общая схема

```
┌─────────────┐
│  Laravel    │  События / уведомления
│  Backend    │  (implements ShouldBroadcast)
└──────┬──────┘
       │ Broadcasting (sync/queue)
┌──────▼───────────────────┐
│   Broadcast Manager      │  routes/broadcasting.php
│ + Queue Worker           │  (redis:queue)
└──────┬───────────────────┘
       │ Reverb протокол
┌──────▼──────┐
│   Reverb    │  Laravel WebSocket сервер (порт 6001)
│   Server    │
└──────┬──────┘
       │ WebSocket
┌──────▼──────────────────────────────────────┐
│         Laravel Echo Client                 │
│  (backend/laravel/resources/js/utils/       │
│              echoClient.ts)                 │
│                                             │
│  - Инициализация соединения                │
│  - Обработка reconnect                     │
│  - Управление состоянием                   │
│  - Экспорт метрик                          │
└──────┬──────────────────────────────────────┘
       │
┌──────▼──────────────────────────────────────┐
│      useWebSocket Composable                │
│  (backend/laravel/resources/js/composables/  │
│              useWebSocket.ts)               │
│                                             │
│  - Подписка на каналы                       │
│  - Reference counting                       │
│  - Resubscribe при reconnect                │
│  - Управление подписками компонентов       │
└──────┬──────────────────────────────────────┘
       │
┌──────▼──────────────────────────────────────┐
│         Vue Components                      │
│  - Zones/Show.vue                           │
│  - Dashboard/Index.vue                      │
│  - HeaderStatusBar.vue                      │
│  - useSystemStatus composable               │
└─────────────────────────────────────────────┘
```

## Функциональные требования

- События телеметрии, статусов команд и алертов должны доходить до UI менее чем за 2 секунды при стабильном соединении.
- Все подписки должны автоматически восстанавливаться после перезапуска браузера, контейнера Laravel или Reverb без участия пользователя.
- Авторизация каналов обязана проходить через Laravel session/Sanctum, а журналирование отказов (`Log::info` в `routes/channels.php`) используется для расследований.
- Клиент обязан корректно работать в dev (через Vite proxy) и prod (через балансировщик/TLS) окружениях с одинаковым кодом.
- Наблюдаемость (системные метрики + браузерные метрики) является частью поставки: без них релиз считается неполным.

### Каналы и авторизация

| Канал | Тип | Источник событий | Авторизация (`routes/channels.php`) | Клиентское использование |
| --- | --- | --- | --- | --- |
| `hydro.alerts` | Public Channel | `AlertCreated` | Любой аутентифицированный пользователь | Глобальная панель алертов (`HeaderStatusBar.vue`) |
| `hydro.devices` | Public Channel | `NodeConfigUpdated` (только без зоны) | Любой аутентифицированный пользователь | Список устройств (unassigned) |
| `hydro.zones.{zoneId}` | Private Channel | `ZoneUpdated`, `NodeConfigUpdated`, `TelemetryBatchUpdated` | Проверка `user !== null`, логирование отказов с `zoneId` | Подписка компонент зоны (`Zones/Show.vue`), realtime телеметрия |
| `commands.{zoneId}` | Private Channel | `CommandStatusUpdated`, `CommandFailed` | Проверка `user !== null` | Карточка команды конкретной зоны, всплывающие статусы |
| `commands.global` | Private Channel | `CommandStatusUpdated`, `CommandFailed` без `zoneId` | Проверка `user !== null` | Глобальный список команд, дашборд |
| `events.global` | Public Channel | `EventCreated` | Публичный канал, авторизация не требуется | Лента событий/активностей |

### События

| Event класс | Broadcast name | Канал | Payload | Очередь |
| --- | --- | --- | --- | --- |
| `AlertCreated` | по умолчанию имя класса | `hydro.alerts` | `alert` (массив) | очередь `broadcasts` (через `ShouldBroadcast`) |
| `NodeConfigUpdated` | `device.updated` | `hydro.zones.{id}` (fallback: `hydro.devices` без зоны) | `device` с ключевыми полями `DeviceNode` | очередь `broadcasts` |
| `TelemetryBatchUpdated` | `telemetry.batch.updated` | `hydro.zones.{id}` | `zone_id`, `updates[]` | очередь `broadcasts` |
| `ZoneUpdated` | по умолчанию имя класса | `hydro.zones.{id}` | `zone.id`, `zone.name`, `zone.status` | очередь `broadcasts` |
| `CommandStatusUpdated` | `CommandStatusUpdated` | `commands.{zoneId}` или `commands.global` | `commandId`, `status`, `message`, `error`, `zoneId` | очередь `broadcasts` |
| `CommandFailed` | `CommandFailed` | `commands.{zoneId}` или `commands.global` | `commandId`, `status=failed`, `message`, `error`, `zoneId` | очередь `broadcasts` |
| `EventCreated` | `EventCreated` | `events.global` | `id`, `kind`, `message`, `zoneId`, `occurredAt` | очередь `broadcasts` |

> Все события используют `ShouldBroadcast` и по умолчанию ставятся в очередь `broadcasts`. Для критичных случаев допускается `ShouldBroadcastNow`, но это должно быть задокументировано в этом файле перед использованием.

## Компоненты системы

### 1. Reverb Server

**Что это:** Laravel WebSocket сервер на собственном протоколе реального времени

**Конфигурация:**
- Порт: 6001 (по умолчанию)
- Переменные окружения:
  - `REVERB_APP_ID` / `REVERB_APP_KEY` / `REVERB_APP_SECRET`
  - `REVERB_SERVER_HOST` / `REVERB_SERVER_PORT` / `REVERB_SERVER_PATH` — параметры процесса `reverb:start`
  - `REVERB_HOST` / `REVERB_PORT` / `REVERB_SCHEME` — клиентские параметры для Echo/Vite
  - `REVERB_ALLOWED_ORIGINS` — список origin через запятую
  - `REVERB_DEBUG`, `REVERB_AUTO_START` — управление логированием и supervisor

**Запуск:**
```bash
php artisan reverb:start
```

**Роль в пайплайне:** Reverb подписывается на `broadcasting` драйвер `reverb` и принимает события, которые Laravel генерирует через `ShouldBroadcast`. Сервер масштабируется горизонтально — несколько узлов могут слушать одну Redis очередь и публиковать события, пока sticky-session включен на балансировщике для WebSocket трафика. Подробнее см. [Laravel Broadcasting 12.x](https://laravel.com/docs/12.x/broadcasting) и [Laravel Reverb](https://laravel.com/docs/reverb).

### 2. Echo Client (echoClient.ts)

**Файл:** `backend/laravel/resources/js/utils/echoClient.ts`

**Ответственность:**
- Инициализация Laravel Echo клиента
- Управление соединением с Reverb
- Обработка переподключений с экспоненциальным backoff
- Отслеживание состояния соединения
- Экспорт метрик (reconnect attempts, last error)

**Ключевые функции:**
- `initEcho(forceReinit?)` - инициализация/переинициализация Echo
- `getEcho()` - получение экземпляра Echo
- `onWsStateChange(listener)` - подписка на изменения состояния
- `getReconnectAttempts()` - количество попыток переподключения
- `getLastError()` - последняя ошибка соединения
- `getConnectionState()` - детальное состояние соединения

**Состояния соединения:**
- `connecting` - подключение в процессе
- `connected` - подключено
- `disconnected` - отключено
- `unavailable` - сервер недоступен
- `failed` - ошибка подключения

**Механизм переподключения:**
- Экспоненциальный backoff: начальная задержка 3 секунды, множитель 1.5, максимум 60 секунд
- Бесконечные попытки переподключения (нет лимита)
- Защита от race conditions через `reconnectLockTime`
- Автоматический вызов `resubscribeAllChannels()` при успешном подключении

### 3. useWebSocket Composable

**Файл:** `backend/laravel/resources/js/composables/useWebSocket.ts`

**Ответственность:**
- Управление подписками на WebSocket каналы
- Reference counting для нескольких компонентов на один канал
- Автоматическая переподписка при reconnect
- Обработка "мертвых" каналов

**Ключевые функции:**
- `subscribeToZoneCommands(zoneId, onCommandUpdate?)` - подписка на команды зоны
- `subscribeToGlobalEvents(onEvent?)` - подписка на глобальные события
- `unsubscribeAll()` - отписка от всех каналов компонента
- `resubscribeAllChannels()` - глобальная функция для переподписки всех каналов

**Reference Counting:**
- Каждый канал имеет счетчик подписчиков (`channelSubscriberCount`)
- При unsubscribe вызывается `stopListening/leave` только если это последний подписчик
- Несколько компонентов могут безопасно подписаться на один канал

**Глобальные реестры:**
- `activeSubscriptions` - массив активных подписок для resubscribe
- `globalChannelSubscriptions` - Map каналов к подпискам компонентов
- `componentSubscriptionsMaps` - WeakMap компонентов к их subscriptions.value
- `channelSubscriberCount` - счетчик подписчиков для каждого канала

### 4. useSystemStatus Composable

**Файл:** `backend/laravel/resources/js/composables/useSystemStatus.ts`

**Ответственность:**
- Мониторинг статуса WebSocket соединения
- Отображение метрик WebSocket (reconnect attempts, last error)
- Debounce для кратковременных разрывов
- Grace period для unavailable состояния

**Метрики:**
- `wsReconnectAttempts` - количество попыток переподключения
- `wsLastError` - последняя ошибка соединения
- `wsConnectionDetails` - детальное состояние соединения

### 5. Vue Components

**Компоненты, использующие WebSocket:**
- `Zones/Show.vue` - подписка на команды зоны
- `Dashboard/Index.vue` - подписка на глобальные события
- `HeaderStatusBar.vue` - отображение статуса и метрик WebSocket

## Конфигурация бекенда

### `config/broadcasting.php`

- Значение `BROADCAST_CONNECTION` берётся из `.env`, по умолчанию `reverb`. В тестах автоматически подставляется `log`, чтобы не открывать реальное соединение (см. условие по `APP_ENV=testing`).
- Секция `connections.reverb` использует `REVERB_APP_KEY`, `REVERB_APP_SECRET`, `REVERB_APP_ID` и клиентские опции (`REVERB_HOST`, `REVERB_PORT`, `REVERB_SCHEME`, `REVERB_CLIENT_PATH`). Любые дополнительные флаги можно передать через `REVERB_CLIENT_OPTIONS` (JSON).
- Секция `connections.pusher` оставлена для обратной совместимости: не используем её, пока не требуется управляемый провайдер.

### `routes/channels.php`

- Каждый приватный канал выполняет проверку `user !== null` и логирует отказ (`Log::info`) с указанием канала, user_id и заголовка `Origin`. Это позволяет быстро расследовать проблемы авторизации.
- Для публичных каналов (`events.global`) Laravel не вызывает авторизацию; если понадобится ограничение доступа, нужно перевести канал в `PrivateChannel` и добавить условие.
- При добавлении новых каналов обязательно описываем их назначение и политику в таблице выше.

### Очереди и `ShouldBroadcast`

- Laravel по умолчанию ставит события в очередь `broadcasts`, если драйвер очередей не `sync`. Для production требуется `QUEUE_CONNECTION=redis` + `php artisan queue:work --queue=broadcasts,default`.
- В dev окружении можно оставлять `QUEUE_CONNECTION=sync`, но перед релизом нужно прогнать пайплайн с Redis очередями для выявления race conditions.
- Любые события, требующие строгого порядка, должны использовать отдельные очереди (например `--queue=commands,broadcasts`). Убедитесь, что это отражено в этом документе прежде чем менять конфиг.

## Backend Broadcasting Pipeline

1. **Генерация события.** Любой доменный сервис диспатчит класс, реализующий `ShouldBroadcast` или `ShouldBroadcastNow`. Класс объявляет канал, название события и payload. Рекомендуется использовать именованные события (`implements ShouldBroadcastNow`) только для критичных путей, остальные идут через очередь.  
2. **Авторизация каналов.** Публичные каналы доступны сразу, для private/presence мы регистрируем правила в `routes/channels.php` (см. [Channel Authorization](https://laravel.com/docs/12.x/broadcasting#authorizing-channels)). Запрос авторизации идет по HTTP с тем же доменом, что и приложение, соответственно CSRF и session middleware уже активны.
3. **Маршрутизация Broadcast.** `config/broadcasting.php` указывает драйвер `reverb` по умолчанию. `BroadcastServiceProvider` регистрирует `Broadcast::routes()` и middleware: auth:sanctum + throttle.
4. **Очереди.** Если событие использует `ShouldBroadcast`, job попадает в Redis очередь `broadcasts`. Worker в контейнере `queue`/`horizon` вытягивает job и публикует payload в Reverb через Reverb API. Для `ShouldBroadcastNow` публикация выполняется синхронно в HTTP потоке (использовать осторожно).
5. **Reverb → Echo.** Reverb получает payload, валидирует подпись и пушит сообщение всем подписчикам канала. Далее работает описанный ранее фронтенд-цепочек `Echo -> useWebSocket -> компоненты`.

Диагностика пайплайна:
- `php artisan queue:failed` — проверка неотправленных событий.
- `php artisan reverb:metrics` — статус WebSocket сервера.
- Vue `useSystemStatus` — подтверждение доставки на клиент.

## Развёртывание Reverb

### Dev (`backend/docker-compose.dev.yml`)

- Контейнер `laravel` публикует порты `80` (HTTP), `5173` (Vite) и `6001` (Reverb). Nginx проксирует WebSocket с `/app/` на Reverb, поэтому в dev не задаём `VITE_REVERB_HOST` — Echo использует текущий origin.
- Переменные окружения `REVERB_*` и `VITE_REVERB_*` уже заданы в compose: ключ `local`, порт `6001`, схема `http`. `REVERB_AUTO_START=true` гарантирует запуск сервиса через supervisor при старте контейнера.
- Для локальной сети нужно установить `VITE_DEV_SERVER_URL=http://<HOST_IP>:5173`, чтобы фронтенд с телефона знал, куда подключаться; Reverb останется доступным по тому же IP:6001.

### Prod (`backend/docker-compose.prod.yml`)

- Контейнер `laravel` слушает `8080` (HTTP) и `6001` (Reverb). Переменные `REVERB_APP_KEY/SECRET` обязательны (см. `:?` в compose). Для браузера `VITE_REVERB_HOST=localhost`, т.к. балансировщик терминирует TLS и отправляет трафик внутрь.
- Ограничения по ресурсам (`cpus`, `memory`) и healthcheck `/api/system/health` помогают Kubernetes/Swarm перезапускать контейнер при сбоях Reverb.
- Дополнительные сервисы (automation-engine, history-logger и т.д.) уже зависят от Laravel, поэтому нет необходимости поднимать отдельный контейнер Reverb.

### Supervisor / systemd

- `backend/laravel/reverb-supervisor.conf` подключается в образ во время сборки и запускает `php artisan reverb:start` от имени пользователя `application`.
- Вне Docker можно использовать тот же конфиг, заменив путь `/app` на путь проекта и включив лог-роатейшн (`stdout_logfile=/var/log/reverb/reverb.log`).
- Для Debian/Ubuntu достаточно создать unit-файл, который стартует `php artisan reverb:start --host=0.0.0.0 --port=6001` после сервиса Redis и Laravel.

### TLS и балансировщик

- Если TLS терминируется на внешнем балансировщике, Reverb продолжает работать по `ws://` внутри внутренней сети. Балансировщик должен проксировать WebSocket (включить `Upgrade`/`Connection` заголовки) к `6001`.
- Для прямого `wss://` на Reverb задаём `REVERB_SCHEME=https`, `REVERB_PORT=443`, копируем сертификаты в контейнер и настраиваем nginx на обратный прокси с `proxy_ssl_certificate`.
- Sticky-сессии необходимы только для HTTP-приложения; Reverb держит собственные WebSocket соединения, поэтому достаточно балансировки по IP:порт без stickiness.

## Авторизация и безопасность каналов

- **Private каналы** (`hydro.zones.{id}`, `commands.{id}`, `commands.global`) — используются, когда данные видны только авторизованным пользователям. Авторизация в `routes/channels.php` проверяет, что пользователь существует, и логирует отказ.
- **Presence каналы** — сейчас не используются, но при необходимости (например, для совместной работы) нужно будет завести `PresenceChannel` и вернуть информацию о пользователе; Laravel автоматически добавит список участников в `Echo.join`.
- **Rate limiting** — применяйте middleware `throttle:60,1` на `Broadcast::routes()` чтобы защититься от флуд-атак на авторизацию.  
- **TLS** — включите `REVERB_TLS=true` и предоставьте сертификаты (либо term на балансировщике) для production.
- **Allowed origins** — держите `REVERB_ALLOWED_ORIGINS` в строгом списке, не используйте `*` вне dev.

## Интеграция фронтенда (Vue + Echo)

### `resources/js/bootstrap.js`

- Точка входа, которая вызывается при загрузке SPA и выполняет `initEcho()` до монтирования Vue-приложения. Это гарантирует, что все composable получат готовый экземпляр Echo.
- Здесь же регистрируются глобальные interceptors Axios и импортируются `useSystemStatus`/telemetry, поэтому любые изменения в подключении должны сначала правиться тут.

### `resources/js/utils/echoClient.ts`

- Единственный владелец экземпляра Laravel Echo. Поддерживает состояния `connecting / connected / disconnected / unavailable / failed` и экспоненциальный backoff (3s → x1.5 → 60s).
- Экспортирует публичные методы `initEcho`, `getEcho`, `onWsStateChange`, `getReconnectAttempts`, `getLastError`, `getConnectionState`.
- Все изменения reconnection-логики и метрик фиксируются в этом файле и обязательно документируются в текущем документе.

### `resources/js/composables/useWebSocket.ts`

- Управляет подписками компонентов: reference counting, resubscribe после reconnect, очистка «мертвых» каналов.
- API: `subscribeToZoneCommands`, `subscribeToGlobalEvents`, `unsubscribeAll`, `resubscribeAllChannels`. Каждый компонент обязан передавать уникальный `componentTag` для диагностики.
- Во время reconnect вызывается `resubscribeAllChannels()` автоматически (инициируется `echoClient`). Если требуется временная подписка, нужно явно удалить запись из `activeSubscriptions`.

### Vue компоненты

- `Zones/Show.vue` — подписывается на `hydro.zones.{id}` и `commands.{id}` через `useWebSocket`, отображает актуальные статусы.
- `Dashboard/Index.vue` — использует глобальные каналы (`events.global`, `commands.global`).
- `HeaderStatusBar.vue` и `useSystemStatus` — визуализируют состояние WebSocket и количество попыток reconnect.
- Любые новые компоненты должны использовать `useWebSocket`, а не напрямую `Echo.channel`, чтобы Reference counting и resubscribe работали автоматически.

### Настройки Vite/Env

- Dev: `VITE_ENABLE_WS=true`, `VITE_REVERB_APP_KEY=local`, остальные `VITE_REVERB_*` оставляем пустыми, чтобы Echo взял текущий origin (`window.location`).
- Prod: на этапе сборки inject’им `VITE_REVERB_HOST`, `VITE_REVERB_PORT`, `VITE_REVERB_SCHEME`, `VITE_WS_TLS`. Эти значения должны совпадать с тем, что видит браузер после балансировщика.
- Если фронтенд вынесен на отдельный домен, необходимо обновить `REVERB_ALLOWED_ORIGINS` и `SANCTUM_STATEFUL_DOMAINS`, иначе авторизация каналов будет отклонена.

## Потоки данных

### Подключение

1. `bootstrap.js` вызывает `initEcho()`
2. `echoClient.ts` создает экземпляр Laravel Echo
3. Echo подключается к Reverb серверу
4. При успешном подключении вызывается `scheduleResubscribe()`
5. `resubscribeAllChannels()` восстанавливает все активные подписки

### Подписка на канал

1. Компонент вызывает `subscribeToZoneCommands(zoneId, handler)`
2. `useWebSocket` проверяет существование канала на Reverb
3. Если канал "мертвый" (нет подписки или слушателей), пересоздается
4. Добавляются обработчики событий через `channel.listen()`
5. Подписка добавляется в `activeSubscriptions` для resubscribe
6. Увеличивается счетчик подписчиков канала

### Получение события

1. Reverb публикует событие в канал
2. Reverb доставляет событие клиенту
3. Laravel Echo вызывает обработчик из `channel.listen()`
4. Обработчик вызывает callback, переданный в `subscribeToZoneCommands()`
5. Компонент обновляет UI

### Переподключение

1. Обнаруживается разрыв соединения (error, failed, unavailable)
2. `attemptReconnect()` запускается с экспоненциальным backoff
3. При успешном переподключении вызывается `scheduleResubscribe()`
4. `resubscribeAllChannels()` восстанавливает все подписки из `activeSubscriptions`
5. Компоненты продолжают получать события без изменений

### Отписка

1. Компонент вызывает `unsubscribe()` или размонтируется
2. Уменьшается счетчик подписчиков канала
3. Если это последний подписчик, вызывается `stopListening()` и `leave()`
4. Подписка удаляется из всех реестров
5. Канал отключается от Reverb



## Best Practices

1. **Всегда используйте `useWebSocket` composable** для подписки на каналы
2. **Не вызывайте `stopListening()` напрямую** - используйте `unsubscribe()`
3. **Передавайте `componentTag`** для лучшей диагностики
4. **Обрабатывайте ошибки** в callback'ах событий
5. **Используйте метрики** из `useSystemStatus` для диагностики проблем

## Дополнительные ресурсы

- [Laravel Broadcasting 12.x](https://laravel.com/docs/12.x/broadcasting)
- [Laravel Reverb Documentation](https://laravel.com/docs/reverb)
- [Laravel Echo Documentation](https://laravel.com/docs/broadcasting#client-side-installation)
