# Диагностика проблемы регистрации узлов

## Проблема
Новая нода отправляет `node_hello`, но не появляется на фронтенде.

## Чеклист диагностики

### 1. Проверить, что history-logger получает node_hello

```bash
cd backend
docker-compose logs history-logger | grep -i "node_hello"
```

Ожидаемый вывод должен содержать:
- `[NODE_HELLO] Received message on topic ...`
- `[NODE_HELLO] Processing node_hello from hardware_id: ...`

Если сообщений нет:
- Проверить, что узел действительно отправляет node_hello
- Проверить MQTT топик (должен быть `hydro/node_hello` или `hydro/+/+/+/node_hello`)
- Проверить, что history-logger подписан на правильный топик (строка 541-542 в main.py)

### 2. Проверить, что history-logger может достучаться до Laravel API

```bash
docker-compose exec history-logger python -c "
import httpx
import asyncio
async def test():
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get('http://laravel/api/system/health', timeout=5.0)
            print(f'Status: {resp.status_code}')
            print(f'Response: {resp.text}')
        except Exception as e:
            print(f'Error: {e}')
asyncio.run(test())
"
```

### 3. Проверить токены

В `docker-compose.dev.yml`:
- Для `history-logger`: `LARAVEL_API_TOKEN=${PY_INGEST_TOKEN:-${PY_API_TOKEN:-}}`
- Для `laravel`: должна быть установлена переменная `PY_INGEST_TOKEN` или `PY_API_TOKEN`

Проверить в контейнере Laravel:
```bash
docker-compose exec laravel php artisan tinker
>>> config('services.python_bridge.ingest_token')
>>> config('services.python_bridge.token')
```

Проверить в контейнере history-logger:
```bash
docker-compose exec history-logger env | grep LARAVEL_API_TOKEN
```

**ВАЖНО**: Если токен установлен в Laravel, он ДОЛЖЕН совпадать с `LARAVEL_API_TOKEN` в history-logger!

### 4. Проверить логи регистрации в Laravel

```bash
docker-compose logs laravel | grep -i "register\|node_hello\|Unauthorized"
```

Если есть ошибки 401 (Unauthorized):
- Проверить, что токены совпадают (см. п. 3)
- Если токен не установлен, убедиться, что он не установлен в обоих местах

### 5. Проверить, что узел создается в БД

```bash
docker-compose exec db psql -U hydro -d hydro_dev -c "SELECT id, uid, hardware_id, type, lifecycle_state, created_at FROM nodes ORDER BY created_at DESC LIMIT 5;"
```

Если узла нет в БД:
- Проверить логи Laravel (см. п. 4)
- Проверить, что метод `registerNodeFromHello` выполняется без ошибок

### 6. Проверить формат node_hello сообщения

Узел должен отправлять JSON в формате:
```json
{
  "message_type": "node_hello",
  "hardware_id": "esp32-XXXXXX",
  "node_type": "ph",
  "fw_version": "1.0.0",
  "capabilities": ["ph", "temperature"],
  "provisioning_meta": {
    "greenhouse_token": "gh-1",
    "zone_id": null,
    "node_name": null
  }
}
```

Проверить топик MQTT:
```bash
docker-compose exec mqtt mosquitto_sub -h localhost -t "hydro/#" -v
```

### 7. Проверить ошибки в history-logger

```bash
docker-compose logs history-logger | grep -i "error\|failed\|exception" | tail -20
```

## Возможные проблемы и решения

### Проблема: Токены не совпадают

**Решение**: Установить одинаковый токен или убрать токен в обоих местах.

В `.env` файле (или переменных окружения):
```bash
PY_INGEST_TOKEN=your-secret-token-here
```

Или убрать токен совсем (если не требуется безопасность):
- В `docker-compose.dev.yml` для history-logger: убрать `LARAVEL_API_TOKEN`
- В Laravel `.env`: не устанавливать `PY_INGEST_TOKEN` и `PY_API_TOKEN`

### Проблема: URL Laravel неправильный

**Решение**: Проверить, что в `docker-compose.dev.yml` для history-logger:
```yaml
LARAVEL_API_URL=http://laravel
```

Если Laravel работает на другом хосте/порту, изменить URL.

### Проблема: node_hello не обрабатывается

**Решение**: Проверить подписку на MQTT топики в `history-logger/main.py` (строки 541-542).

Должны быть подписки:
```python
await mqtt.subscribe("hydro/node_hello", handle_node_hello)
await mqtt.subscribe("hydro/+/+/+/node_hello", handle_node_hello)
```

### Проблема: Узел создается, но не отображается на фронте

**Решение**: 
1. Проверить, что фронтенд запрашивает узлы через API
2. Проверить, что кеш очищается после регистрации (в `NodeRegistryService::registerNodeFromHello` используется `Cache::flush()`)
3. Проверить фильтры на фронте (возможно, показываются только узлы с `zone_id`)

## Быстрая проверка

Запустить все проверки сразу:
```bash
echo "=== 1. History-logger logs ==="
docker-compose logs history-logger --tail=50 | grep -i "node_hello"

echo "=== 2. Laravel logs ==="
docker-compose logs laravel --tail=50 | grep -i "register\|node_hello\|Unauthorized"

echo "=== 3. DB nodes ==="
docker-compose exec db psql -U hydro -d hydro_dev -c "SELECT id, uid, hardware_id, type, lifecycle_state FROM nodes ORDER BY created_at DESC LIMIT 5;"

echo "=== 4. Tokens ==="
echo "History-logger token:"
docker-compose exec history-logger env | grep LARAVEL_API_TOKEN || echo "NOT SET"
echo "Laravel expected token (ingest):"
docker-compose exec laravel php artisan tinker --execute="echo config('services.python_bridge.ingest_token') ?? 'NOT SET';" | tail -1
```

