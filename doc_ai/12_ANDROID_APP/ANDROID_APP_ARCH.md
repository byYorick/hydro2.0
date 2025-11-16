# ANDROID_APP_ARCH.md
# Архитектура Android-приложения Hydro 2.0
# Provisioning • Мониторинг • Управление • Оповещения

Документ описывает архитектуру Android-приложения,
которое используется для:

- первичной настройки узлов (Wi-Fi provisioning),
- мониторинга теплиц и зон,
- приёма алертов,
- базового управления.

---

## 1. Технологический стек

Рекомендуемый стек:

- Язык: **Kotlin**
- UI: **Jetpack Compose**
- Архитектура: **MVVM + Clean Architecture** (слои: data, domain, presentation)
- DI: **Hilt**
- Сетевое API: **Retrofit + OkHttp**
- WebSocket/MQTT: клиент поверх MQTT-брокера или WebSocket-bridge backend’а
- Хранение:
 - локальный кэш: Room / DataStore
 - secure-хранилище токенов (Android Keystore)

---

## 2. Слои приложения

### 2.1. Presentation (UI + ViewModel)

- Экраны Compose:
 - Provisioning flow
 - Список теплиц/зон
 - Детальный экран зоны
 - Экран узла
 - Экран алертов/журнала событий
 - Настройки пользователя

- ViewModel’ы:
 - `ProvisioningViewModel`
 - `GreenhousesViewModel`
 - `ZoneDetailsViewModel`
 - `NodeDetailsViewModel`
 - `AlertsViewModel`

### 2.2. Domain

- Use case’ы:
 - `StartProvisioningUseCase`
 - `CompleteProvisioningUseCase`
 - `GetGreenhousesUseCase`
 - `GetZoneDetailsUseCase`
 - `GetNodeDetailsUseCase`
 - `AcknowledgeAlertUseCase`
 - `UpdateNodeConfigUseCase`

### 2.3. Data

- Репозитории:
 - `NodesRepository`
 - `ZonesRepository`
 - `AlertsRepository`
 - `UserSettingsRepository`

- Источники данных:
 - REST API (backend)
 - WebSocket/SignalR/MQTT-bridge
 - локальная БД (Room) и кэш.

---

## 3. Основные функции приложения

1. **Provisioning узлов**
 - поиск узла по Wi-Fi (SSID типа `HYDRO-NODE-XXXX`);
 - подключение к AP узла;
 - конфигурирование Wi-Fi и привязки;
 - передача данных на узел через HTTP (`/configure`).

2. **Авторизация и мульти-теплицы**
 - логин пользователя (email/пароль или другой метод);
 - выбор активной теплицы (если их несколько).

3. **Мониторинг**
 - список зон с ключевыми метриками;
 - деталка зоны:
 - текущие pH/EC/температура/влажность;
 - состояние исполнительных устройств;
 - активный рецепт.

4. **Оповещения и события**
 - push-уведомления;
 - список алертов;
 - подтверждение/закрытие алертов (если предусмотрено бизнес-логикой).

5. **Базовое управление**
 - режимы: ручной/авто;
 - изменение целевых значений в рецептах (при наличии прав);
 - временная пауза/остановка подачи раствора, света и т.п.

---

## 4. Взаимодействие с backend

См. `ANDROID_APP_API_INTEGRATION.md`.

Основной принцип:

- все долгоживущие состояния (телеметрия, статусы узлов, рецепты)
 приходят от backend:
 - либо по REST (pull),
 - либо через WebSocket/stream (push).

Приложение **не общается с узлами напрямую**, кроме режима provisioning.

---

## 5. Требования к ИИ-агенту

1. ИИ должен создавать новые экраны и ViewModel’ы в соответствии с этой архитектурой.
2. Нельзя шить бизнес-логику напрямую в Compose-экраны — только через ViewModel.
3. Любые изменения в API-интерфейсах должны быть согласованы с
 `API_SPEC_FRONTEND_BACKEND_FULL.md` и `ANDROID_APP_API_INTEGRATION.md`.
