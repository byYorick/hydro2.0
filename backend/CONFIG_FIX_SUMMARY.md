# Исправление ошибки валидации конфига

## Проблема
Конфиг не проходил валидацию с ошибкой: `Missing or invalid mqtt.host`

## Причина
1. **В `PublishNodeConfigJob`** конфиг генерировался без `includeCredentials = true`, что приводило к генерации MQTT секции только с `{"configured": true}` без обязательных полей `host` и `port`.

2. **В `NodeConfigService::getMqttConfig()`** если в `$node->config` уже была секция `mqtt` с `{"configured": true}`, она возвращалась как есть, даже при `includeCredentials = true`.

3. **В `config/services.php`** отсутствовали настройки MQTT (`services.mqtt.host`, `services.mqtt.port`, etc.).

## Исправления

### 1. Исправлен `PublishNodeConfigJob.php`
```php
// Было:
$config = $configService->generateNodeConfig($node);

// Стало:
$config = $configService->generateNodeConfig($node, null, true);
```

### 2. Исправлена логика в `NodeConfigService::getMqttConfig()`
Теперь всегда генерируется полная конфигурация из глобальных настроек, даже если в `$node->config` есть `mqtt` секция. Это предотвращает возврат неполной конфигурации `{"configured": true}`.

### 3. Добавлены настройки MQTT в `config/services.php`
```php
'mqtt' => [
    'host' => env('MQTT_HOST', '192.168.1.115'),
    'port' => env('MQTT_PORT', 1883),
    'keepalive' => env('MQTT_KEEPALIVE', 30),
    'username' => env('MQTT_USERNAME'),
    'password' => env('MQTT_PASSWORD'),
    'client_id' => env('MQTT_CLIENT_ID'),
],
```

## Результат
- Конфиг теперь содержит полную MQTT конфигурацию с полями `host`, `port`, `keepalive`
- Валидация конфига должна проходить успешно
- Laravel контейнер перезапущен, кеш очищен

## Следующие шаги
При следующей отправке конфига ноде, он должен содержать полную MQTT конфигурацию и пройти валидацию.

