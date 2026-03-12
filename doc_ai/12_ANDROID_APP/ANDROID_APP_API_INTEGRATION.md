# ANDROID_APP_API_INTEGRATION.md
# Интеграция Android-приложения с backend и узлами

Документ описывает, как Android-приложение общается с системой:

- с backend (Laravel);
- косвенно — с узлами ESP32 через режим provisioning.

---

## 1. Взаимодействие с backend

### 1.1. REST API

Android использует те же REST-эндпоинты, что и веб-frontend, через `/api/*`:

- `/api/auth/login` — авторизация;
- `/api/greenhouses`, `/api/zones`, `/api/nodes` — список и детали;
- `/api/zones/{id}/telemetry/last` — последние значения;
- `/api/zones/{id}/telemetry/history` — графики;
- `/api/zones/{id}/commands` — команды на зону;
- `/api/nodes/{id}/commands` — локальные команды (калибровка и т.п.).

Аутентификация: передача токена в заголовке `Authorization: Bearer <token>`.

### 1.2. Realtime (по желанию)

Возможны два варианта:

1. **WebSocket (Laravel WebSockets)** — подписка на каналы зон/узлов.
2. **Polling** — периодические запросы к REST API для обновления данных.

В первой версии достаточно polling, позже можно добавить WebSocket.

---

## 2. Режим provisioning узлов (первая настройка)

Android-приложение используется для первичной настройки узлов ESP32:

1. Узел при первом запуске входит в режим AP (`HYDRO-SETUP`).
2. Пользователь подключается к этому Wi-Fi со смартфона.
3. Android-приложение сканирует доступные узлы (по имени сети или mDNS/HTTP-запросу).
4. Приложение открывает локальный HTTP-endpoint узла (например, `http://192.168.4.1/api/provision`)
 и передаёт:

```json
{
 "wifi_ssid": " ",
 "wifi_password": " ",
 "backend_base_url": "https://your-backend",
 "gh_uid": "gh-main",
 "zone_uid": "zone-a"
}
```

5. Узел сохраняет настройки в NVS и перезагружается.
6. После успешного подключения к Wi-Fi и MQTT узел сообщает о себе через
 `hydro/system/announce/{node_uid}`.

---

## 3. UX-паттерны в Android

Основные экраны (см. `ANDROID_APP_SCREENS.md`):

- список теплиц/зон;
- карточка зоны (графики, текущие значения);
- список алертов;
- экран команды/действия;
- мастер настройки нового узла (provisioning).

---

## 4. Правила для ИИ-агентов

1. Не хардкодить URL-адреса backend-сервера — они должны быть настраиваемыми.
2. Следить за тем, чтобы формат API-запросов соответствовал backend-документации
 (`API_SPEC_FRONTEND_BACKEND_FULL.md`, `REST_API_REFERENCE.md`).
3. Любые изменения протокола provisioning отражать в этом документе и на стороне прошивки узла.

Android-приложение — это прежде всего **клиент backend-API** и удобный инструмент настройки узлов, а не прямой «контроллер» оборудования.
