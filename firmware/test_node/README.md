# Тестовая прошивка для E2E тестов

Упрощенная прошивка для проверки совместимости форматов сообщений с эталоном node-sim.

## Назначение

Эта прошивка предназначена для:
- Проверки форматов сообщений MQTT
- Валидации соответствия эталону node-sim
- E2E тестирования совместимости

## Функциональность

Прошивка публикует:
- **Телеметрию** каждые 5 секунд (ph, ec, air_temp_c, air_rh)
- **Heartbeat** каждые 15 секунд
- **Статус** при старте и периодически
- **Ответы на команды** в правильном формате

## Компиляция

```bash
cd firmware/test_node
source /home/georgiy/esp/esp-idf/export.sh
idf.py build
```

## Использование

1. Загрузите прошивку на устройство
2. Настройте WiFi и MQTT в конфигурации
3. Запустите тест совместимости:

```bash
# Используйте скрипт запуска тестов
./firmware/tests/run_compatibility_tests.sh

# Или напрямую
python3 firmware/tests/test_node_compatibility.py \
    --mqtt-host localhost \
    --mqtt-port 1884 \
    --gh-uid gh-test-1 \
    --zone-uid zn-test-1 \
    --node-uid nd-test-001
```

## Форматы сообщений

Все сообщения соответствуют эталону node-sim:
- Телеметрия: `{metric_type, value, ts}`
- Ответы на команды: `{cmd_id, status, details?, ts}`
- Heartbeat: `{uptime, free_heap, rssi?}`
- Статус: `{status, ts}`

Подробнее о тестах: [`../tests/README.md`](../tests/README.md)

---

**Версия:** 1.0

