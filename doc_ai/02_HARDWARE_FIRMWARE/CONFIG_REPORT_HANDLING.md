# Обработка config_report от ноды

**Дата:** 2026-03-02


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: legacy форматы/алиасы удалены, обратная совместимость не поддерживается.

---

## Изменение логики привязки ноды

Нода считается привязанной к зоне только после фактического подтверждения от устройства через
`config_report` из целевого namespace.

---

## Поток привязки ноды

1. **Пользователь привязывает ноду к зоне** через UI
   - backend выставляет intent (`pending_zone_id` / `zone_id` в зависимости от сценария)
   - запускается publish NodeConfig в устройство через pipeline:
     `Laravel -> PublishNodeConfigJob -> history-logger -> MQTT .../config -> node`

2. **Нода принимает `.../config`, применяет и публикует `config_report`**
   - входной топик config: `hydro/{gh}/{zone}/{node}/config` (или temp namespace)
   - исходящий snapshot: `hydro/{gh}/{zone}/{node}/config_report`
   - payload содержит полный актуальный NodeConfig из NVS

3. **history-logger обрабатывает `config_report`**
   - Сохраняет конфиг в `nodes.config`
   - Синхронизирует `node_channels` из payload
   - Завершает binding только если `config_report` пришёл из целевого namespace и соответствует intent

4. **Нода переводится в целевое состояние binding**
   - только после подтверждённого `config_report`
   - fail-closed: без подтверждения binding не финализируется

---

## Измененные файлы

### 1. history-logger
- ✅ Подписка и обработка `hydro/+/+/+/config_report`
- ✅ Сохранение `nodes.config` и синхронизация `node_channels`
- ✅ Endpoint публикации config в ноду: `POST /nodes/{node_uid}/config`

### 2. Laravel
- ✅ Endpoint `POST /api/nodes/{node}/config/publish` активен
- ✅ Публикация выполняется асинхронно через `PublishNodeConfigJob`
- ✅ Job вызывает history-logger API, прямой MQTT publish из Laravel отсутствует

---

## Преимущества

1. ✅ **Источник факта на устройстве** — итоговый config подтверждается `config_report` от ноды
2. ✅ **Надежность** — привязка подтверждается фактом получения config_report
3. ✅ **Согласованность** — каналы синхронизируются из реального payload ноды
4. ✅ **Управляемость** — backend может инициировать publish config без обхода защищённого pipeline

---

## Метрики

Отдельные метрики для `config_report` пока не заведены.

---

## Важные замечания

- Если нода не отправила `config_report`, binding не финализируется.
- `config_report` остаётся источником подтверждения фактической конфигурации на устройстве.
- Endpoint `config/publish` не заменяет `config_report`; он только инициирует доставку config к ноде.
