# Сидеры для всех Grafana Dashboards

## Быстрый старт

Для заполнения всех таблиц для проверки всех Grafana dashboards:

```bash
docker exec backend-laravel-1 php artisan migrate:fresh --seed
```

Или пошагово:

```bash
# 1. Базовые данные (зоны, узлы, рецепты)
docker exec backend-laravel-1 php artisan db:seed --class=DemoDataSeeder

# 2. Телеметрия (для History Logger)
docker exec backend-laravel-1 php artisan db:seed --class=TelemetrySeeder

# 3. Все данные для dashboards (команды, алерты, события, статусы)
docker exec backend-laravel-1 php artisan db:seed --class=ComprehensiveDashboardSeeder
```

## Созданные данные

### ✅ Alerts Dashboard
- **105 алертов** (22 активных, 56 решенных)
- Различные типы: pH, EC, температура, влажность, узлы, насосы

### ✅ Automation Engine Service
- **416 команд** с различными статусами
- Распределение: pending (17), sent (87), ack (285), failed (27)
- Команды за последние 7 дней

### ✅ Commands & Automation
- Те же **416 команд** с детальной статистикой
- Группировка по типам и статусам

### ✅ History Logger Service
- **34,316 записей телеметрии** (samples)
- **20 последних значений** (telemetry_last)
- Данные за последние 30 дней

### ✅ Node Status
- **6 узлов** (1 online, 5 offline)
- Метрики: uptime, memory, WiFi signal
- Временные метки последнего контакта

### ✅ System Overview
- Общая статистика всех компонентов
- Статусы сервисов
- Сводные метрики

### ✅ Zone Telemetry
- **810 событий зон** за последние 7 дней
- Типы: корректировки, полив, переходы фаз, освещение

## Проверка dashboards

После выполнения сидеров откройте Grafana:

1. **Alerts Dashboard** → Должны быть видны активные и решенные алерты
2. **Automation Engine Service** → Команды по зонам и типам
3. **Commands & Automation** → Статистика команд
4. **History Logger Service** → Поток телеметрии и метрики
5. **Node Status** → Статусы узлов (online/offline)
6. **System Overview** → Общая статистика
7. **Zone Telemetry** → События зон на временной шкале

## Статистика после выполнения

```
Зоны: 4
Узлы: 6 (1 online, 5 offline)
Команды: 416
Алерты: 105 (22 активных)
События: 810
Телеметрия (samples): 34,316
Телеметрия (last): 20
```

## Дополнительная информация

- **ComprehensiveDashboardSeeder** - основной сидер для всех dashboards
- **TelemetrySeeder** - создает историю телеметрии
- **DemoDataSeeder** - создает базовые данные (зоны, узлы, рецепты)

Подробнее см.:
- `README_COMPREHENSIVE_DASHBOARD_SEEDER.md` - детальное описание
- `README_TELEMETRY_SEEDERS.md` - описание сидеров телеметрии

