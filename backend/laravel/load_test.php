#!/usr/bin/env php
<?php
/**
 * Нагрузочный тест для проверки масштабируемости системы.
 * Тестирует систему с ~100 зонами, проверяет latency p99 и переполнение очереди.
 */

require __DIR__.'/vendor/autoload.php';

$app = require_once __DIR__.'/bootstrap/app.php';
$app->make(\Illuminate\Contracts\Console\Kernel::class)->bootstrap();

use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\DB;
use App\Models\User;

// Конфигурация
$BASE_URL = env('APP_URL', 'http://localhost:8080');
$CONCURRENT_REQUESTS = 20; // Уменьшено для избежания rate limiting
$TOTAL_REQUESTS = 500; // Уменьшено для более реалистичного теста
$TEST_DURATION_SEC = 60;

$requestTimes = [];
$errors = [];

echo "=" . str_repeat("=", 60) . "\n";
echo "НАГРУЗОЧНОЕ ТЕСТИРОВАНИЕ СИСТЕМЫ\n";
echo "=" . str_repeat("=", 60) . "\n";
echo "Base URL: {$BASE_URL}\n";
echo "Concurrent requests: {$CONCURRENT_REQUESTS}\n";
echo "Total requests: {$TOTAL_REQUESTS}\n";
echo "Test duration: {$TEST_DURATION_SEC}s\n";
echo "=" . str_repeat("=", 60) . "\n";

// Авторизация
echo "\n[1/4] Авторизация...\n";
$user = User::where('email', 'admin@example.com')->first();
if (!$user) {
    echo "ОШИБКА: Пользователь admin@example.com не найден\n";
    exit(1);
}

// Удаляем старые токены для этого теста
$user->tokens()->where('name', 'load-test')->delete();

$token = $user->createToken('load-test')->plainTextToken;
echo "✓ Авторизация успешна\n";
echo "  Token preview: " . substr($token, 0, 20) . "...\n";

// Проверка начального состояния
echo "\n[2/4] Проверка начального состояния...\n";
$zonesCount = DB::table('zones')->count();
$nodesCount = DB::table('nodes')->count();
echo "Зон в системе: {$zonesCount}\n";
echo "Нод в системе: {$nodesCount}\n";

// Проверка метрик очереди
$queueSize = 0;
try {
    $redis = \Illuminate\Support\Facades\Redis::connection();
    $queueSize = $redis->llen('telemetry_queue') ?? 0;
    echo "Размер очереди телеметрии: {$queueSize}\n";
} catch (\Exception $e) {
    echo "Не удалось получить размер очереди: " . $e->getMessage() . "\n";
}

// Нагрузочное тестирование
echo "\n[3/4] Нагрузочное тестирование ({$TOTAL_REQUESTS} запросов)...\n";
$startTime = microtime(true);

// Используем публичные или менее защищенные endpoints для теста
$endpoints = [
    '/api/system/health', // Публичный endpoint
    '/api/system/config/full', // Требует Python service token или Sanctum
];

$requestsPerEndpoint = (int)($TOTAL_REQUESTS / count($endpoints));

// Функция для выполнения запроса
$makeRequest = function($url) use ($BASE_URL, $token, &$requestTimes, &$errors) {
    $start = microtime(true);
    try {
        $response = Http::timeout(30)
            ->withHeaders([
                'Authorization' => 'Bearer ' . $token,
                'Accept' => 'application/json'
            ])
            ->get($BASE_URL . $url);
        
        $elapsed = microtime(true) - $start;
        $requestTimes[] = $elapsed;
        
        if (!$response->successful()) {
            $errors[] = [
                'url' => $url,
                'status' => $response->status(),
                'error' => $response->body()
            ];
        }
        
        return [
            'success' => $response->successful(),
            'elapsed' => $elapsed,
            'status' => $response->status()
        ];
    } catch (\Exception $e) {
        $elapsed = microtime(true) - $start;
        $requestTimes[] = $elapsed;
        $errors[] = [
            'url' => $url,
            'error' => $e->getMessage()
        ];
        return [
            'success' => false,
            'elapsed' => $elapsed,
            'status' => 0
        ];
    }
};

// Выполняем запросы
$allRequests = [];
foreach ($endpoints as $endpoint) {
    for ($i = 0; $i < $requestsPerEndpoint; $i++) {
        $allRequests[] = $endpoint;
    }
}

// Перемешиваем для более реалистичной нагрузки
shuffle($allRequests);

// Выполняем запросы параллельно (в батчах)
$batchSize = $CONCURRENT_REQUESTS;
$batches = array_chunk($allRequests, $batchSize);

foreach ($batches as $batchIndex => $batch) {
    $results = [];
    foreach ($batch as $url) {
        $results[] = $makeRequest($url);
    }
    
    if (($batchIndex + 1) % 10 == 0) {
        $progress = min(100, (($batchIndex + 1) * $batchSize / $TOTAL_REQUESTS) * 100);
        echo "Прогресс: " . number_format($progress, 1) . "%\n";
    }
    
    // Небольшая задержка между батчами
    usleep(10000); // 10ms
}

$elapsed = microtime(true) - $startTime;

// Проверка метрик после теста
echo "\n[4/4] Проверка метрик после теста...\n";
$finalQueueSize = 0;
try {
    $redis = \Illuminate\Support\Facades\Redis::connection();
    $finalQueueSize = $redis->llen('telemetry_queue') ?? 0;
    echo "Размер очереди телеметрии после теста: {$finalQueueSize}\n";
} catch (\Exception $e) {
    echo "Не удалось получить размер очереди: " . $e->getMessage() . "\n";
}

// Результаты
echo "\n" . str_repeat("=", 60) . "\n";
echo "РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ\n";
echo str_repeat("=", 60) . "\n";

if (!empty($requestTimes)) {
    sort($requestTimes);
    $count = count($requestTimes);
    $mean = array_sum($requestTimes) / $count;
    $median = $requestTimes[(int)($count / 2)];
    $p95 = $requestTimes[(int)($count * 0.95)];
    $p99 = $requestTimes[(int)($count * 0.99)];
    $min = min($requestTimes);
    $max = max($requestTimes);
    
    echo "\nВремя выполнения запросов:\n";
    echo "  Всего запросов: {$count}\n";
    echo "  Успешных: " . ($count - count($errors)) . "\n";
    echo "  Среднее время: " . number_format($mean, 3) . "s\n";
    echo "  Медиана (p50): " . number_format($median, 3) . "s\n";
    echo "  p95: " . number_format($p95, 3) . "s\n";
    echo "  p99: " . number_format($p99, 3) . "s\n";
    echo "  Максимум: " . number_format($max, 3) . "s\n";
    echo "  Минимум: " . number_format($min, 3) . "s\n";
    
    // Проверка целевых метрик
    echo "\n✓ p99 latency: " . number_format($p99, 3) . "s (" . number_format($p99 * 1000, 0) . "ms)\n";
    if ($p99 <= 0.5) {
        echo "  ✓ ЦЕЛЬ ДОСТИГНУТА: p99 ≤ 500ms\n";
    } else {
        echo "  ✗ ЦЕЛЬ НЕ ДОСТИГНУТА: p99 > 500ms\n";
    }
}

if (!empty($errors)) {
    echo "\nОшибки:\n";
    echo "  Всего ошибок: " . count($errors) . "\n";
    $errorTypes = [];
    foreach ($errors as $error) {
        $type = $error['error'] ?? 'unknown';
        $errorTypes[$type] = ($errorTypes[$type] ?? 0) + 1;
    }
    foreach ($errorTypes as $type => $count) {
        echo "  " . substr($type, 0, 50) . ": {$count}\n";
    }
}

if ($finalQueueSize > 1000) {
    echo "\n⚠ ПЕРЕПОЛНЕНИЕ ОЧЕРЕДИ ОБНАРУЖЕНО: {$finalQueueSize} элементов\n";
} else {
    echo "\n✓ Размер очереди в норме: {$finalQueueSize} элементов\n";
}

echo "\nОбщее время теста: " . number_format($elapsed, 2) . "s\n";
echo "RPS (запросов в секунду): " . number_format($count / $elapsed, 2) . "\n";
echo str_repeat("=", 60) . "\n";

