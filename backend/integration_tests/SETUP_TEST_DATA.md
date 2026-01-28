# Настройка тестовых данных для интеграционных тестов

## Описание

Перед запуском интеграционных тестов необходимо создать тестовые данные в БД:
- Тестовый greenhouse (`gh-test-1`)
- Тестовую zone (`zn-test-1`)
- 6 тестовых нод (ph, ec, pump, climate, relay, light)

## Автоматическое создание

Тестовые данные создаются автоматически при первом запуске тестов через Laravel tinker.

## Ручное создание

### Через Laravel tinker

```bash
cd backend
docker exec backend-laravel-1 php artisan tinker --execute="
// Создаем тестовый greenhouse
\$gh = \App\Models\Greenhouse::firstOrCreate(
    ['uid' => 'gh-test-1'],
    [
        'name' => 'Test Greenhouse',
        'type' => 'indoor',
        'timezone' => 'UTC',
        'provisioning_token' => 'test-token-12345'
    ]
);

// Создаем тестовую zone
\$zone = \App\Models\Zone::firstOrCreate(
    ['uid' => 'zn-test-1'],
    [
        'greenhouse_id' => \$gh->id,
        'name' => 'Test Zone',
        'status' => 'online'
    ]
);

// Создаем тестовые ноды
\$nodes = [
    ['uid' => 'nd-ph-test-1', 'type' => 'ph', 'name' => 'Test PH Node'],
    ['uid' => 'nd-ec-test-1', 'type' => 'ec', 'name' => 'Test EC Node'],
    ['uid' => 'nd-pump-test-1', 'type' => 'pump', 'name' => 'Test Pump Node'],
    ['uid' => 'nd-climate-test-1', 'type' => 'climate', 'name' => 'Test Climate Node'],
    ['uid' => 'nd-relay-test-1', 'type' => 'relay', 'name' => 'Test Relay Node'],
    ['uid' => 'nd-light-test-1', 'type' => 'light', 'name' => 'Test Light Node'],
];

foreach (\$nodes as \$nodeData) {
    \App\Models\DeviceNode::firstOrCreate(
        ['uid' => \$nodeData['uid']],
        [
            'zone_id' => \$zone->id,
            'name' => \$nodeData['name'],
            'type' => \$nodeData['type'],
            'status' => 'online',
            'lifecycle_state' => 'ACTIVE',
            'error_count' => 0,
            'warning_count' => 0,
            'critical_count' => 0,
        ]
    );
}
"
```

## Очистка тестовых данных

### Через Laravel tinker

```bash
docker exec backend-laravel-1 php artisan tinker --execute="
// Удаляем тестовые ноды
\App\Models\DeviceNode::whereIn('uid', [
    'nd-ph-test-1', 'nd-ec-test-1', 'nd-pump-test-1',
    'nd-climate-test-1', 'nd-relay-test-1', 'nd-light-test-1'
])->delete();

// Удаляем тестовую zone
\App\Models\Zone::where('uid', 'zn-test-1')->delete();

// Удаляем тестовый greenhouse
\App\Models\Greenhouse::where('uid', 'gh-test-1')->delete();
"
```

## Проверка тестовых данных

```bash
docker exec backend-laravel-1 php artisan tinker --execute="
\$nodes = \App\Models\DeviceNode::whereIn('uid', [
    'nd-ph-test-1', 'nd-ec-test-1', 'nd-pump-test-1',
    'nd-climate-test-1', 'nd-relay-test-1', 'nd-light-test-1'
])->get(['uid', 'name', 'type', 'status']);

echo 'Found ' . \$nodes->count() . ' test nodes' . PHP_EOL;
foreach (\$nodes as \$node) {
    echo \$node->uid . ' - ' . \$node->name . ' (' . \$node->type . ', ' . \$node->status . ')' . PHP_EOL;
}
"
```

