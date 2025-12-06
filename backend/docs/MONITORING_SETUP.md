# Настройка автоматического импорта Dashboards в Grafana

## Проблема

Dashboards не появляются автоматически в Grafana после запуска.

## Решение

### 1. Проверьте структуру директорий

Убедитесь, что существуют следующие файлы:

```
backend/configs/dev/grafana/
├── provisioning/
│   └── dashboards/
│       └── dashboards.yml  ← должен быть создан
├── dashboards/
│   ├── history-logger.json
│   ├── automation-engine.json
│   └── ...
└── datasources.yml
```

### 2. Перезапустите Grafana

```bash
# Для dev окружения
docker-compose -f backend/docker-compose.dev.yml restart grafana

# Для prod окружения
docker-compose -f backend/docker-compose.prod.yml restart grafana
```

### 3. Проверьте логи Grafana

```bash
docker logs grafana | grep -i dashboard
```

Должны увидеть сообщения об импорте dashboards.

### 4. Если dashboards всё ещё не появились

**Вариант А: Ручной импорт через UI**

1. Откройте Grafana: `http://localhost:3000`
2. Войдите (admin/admin для dev)
3. Меню → **Dashboards** → **Import**
4. Нажмите **Upload JSON file**
5. Выберите файл из `backend/configs/dev/grafana/dashboards/`
6. Нажмите **Load** → **Import**

**Вариант Б: Проверьте права доступа**

Убедитесь, что файлы доступны для чтения:

```bash
chmod -R 644 backend/configs/*/grafana/dashboards/*.json
```

**Вариант В: Проверьте конфигурацию provisioning**

Откройте `backend/configs/dev/grafana/provisioning/dashboards/dashboards.yml` и убедитесь, что путь правильный:

```yaml
options:
  path: /var/lib/grafana/dashboards
```

### 5. Проверьте монтирование volumes в docker-compose

Убедитесь, что в `docker-compose.dev.yml` и `docker-compose.prod.yml` есть:

```yaml
volumes:
  - ./configs/dev/grafana/provisioning/dashboards:/etc/grafana/provisioning/dashboards:ro
  - ./configs/dev/grafana/dashboards:/var/lib/grafana/dashboards:ro
```

## После настройки

Dashboards должны автоматически импортироваться при каждом запуске Grafana. Новые dashboards в директории `dashboards/` будут автоматически подхватываться каждые 10 секунд (согласно `updateIntervalSeconds` в `dashboards.yml`).

