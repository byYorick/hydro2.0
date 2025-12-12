<?php

use App\Http\Controllers\AiController;
use App\Http\Controllers\AlertController;
use App\Http\Controllers\AlertStreamController;
use App\Http\Controllers\AuthController;
use App\Http\Controllers\GreenhouseController;
use App\Http\Controllers\NodeCommandController;
use App\Http\Controllers\NodeController;
use App\Http\Controllers\PresetController;
use App\Http\Controllers\ProfitabilityController;
use App\Http\Controllers\PythonIngestController;
use App\Http\Controllers\RecipeController;
use App\Http\Controllers\RecipePhaseController;
use App\Http\Controllers\ReportController;
use App\Http\Controllers\ServiceLogController;
use App\Http\Controllers\SimulationController;
use App\Http\Controllers\SystemController;
use App\Http\Controllers\TelemetryController;
use App\Http\Controllers\ZoneCommandController;
use App\Http\Controllers\ZoneController;
use App\Http\Controllers\ZonePidConfigController;
use App\Http\Controllers\ZonePidLogController;
use App\Http\Controllers\UnassignedNodeErrorController;
use Illuminate\Support\Facades\Route;

// Auth роуты с более строгим rate limiting для предотвращения брутфорса
Route::prefix('auth')->middleware('throttle:10,1')->group(function () {
    Route::post('/login', [AuthController::class, 'login']);
    Route::post('/logout', [AuthController::class, 'logout'])->middleware('auth:sanctum');
    Route::get('/me', [AuthController::class, 'me'])->middleware('auth:sanctum');
});

// Публичные системные эндпоинты
// Health check имеет более высокий лимит для мониторинга (300 запросов в минуту для поддержки множественных компонентов)
// Добавляем middleware сессий и аутентификации, чтобы определить, залогинен ли пользователь
// (но не требуем аутентификацию - роут остается публичным)
Route::get('system/health', [SystemController::class, 'health'])
    ->middleware([
        \Illuminate\Cookie\Middleware\EncryptCookies::class,
        \Illuminate\Session\Middleware\StartSession::class,
        \App\Http\Middleware\AuthenticateWithApiToken::class, // Попытка аутентификации через токен (необязательно)
        'throttle:300,1',
    ]);
// configFull доступен для Python сервисов через токен или для авторизованных пользователей через Sanctum
Route::middleware('throttle:30,1')->group(function () {
    // Используем middleware, который проверяет либо Sanctum токен, либо Python service token
    Route::get('system/config/full', [SystemController::class, 'configFull'])
        ->middleware('verify.python.service');
});

// API routes for Inertia (using session authentication)
// Note: Session middleware is added here for routes that use session-based auth
// EncryptCookies must come before StartSession
// CSRF protection is handled globally in bootstrap/app.php with exceptions for token-based routes
// Rate limiting: 60 requests per minute (default from bootstrap/app.php)
Route::middleware([
    \Illuminate\Cookie\Middleware\EncryptCookies::class,
    \Illuminate\Session\Middleware\StartSession::class,
    \App\Http\Middleware\AuthenticateWithApiToken::class,
    'auth',
    'throttle:120,1', // Увеличен лимит до 120 запросов в минуту для поддержки множественных компонентов
])->group(function () {
    // Read-only endpoints (viewer+)
    Route::get('greenhouses', [GreenhouseController::class, 'index']);
    Route::get('greenhouses/{greenhouse}', [GreenhouseController::class, 'show']);
    Route::get('zones', [ZoneController::class, 'index']);
    Route::get('zones/{zone}', [ZoneController::class, 'show']);
    Route::get('zones/{zone}/health', [ZoneController::class, 'health']);
    Route::get('zones/{zone}/cycles', [ZoneController::class, 'cycles']);
    Route::get('nodes', [NodeController::class, 'index']);
    Route::get('nodes/{node}', [NodeController::class, 'show']);
    Route::get('nodes/{node}/config', [NodeController::class, 'getConfig']);
    Route::get('nodes/{node}/lifecycle/allowed-transitions', [NodeController::class, 'getAllowedTransitions']);
    Route::get('unassigned-node-errors', [UnassignedNodeErrorController::class, 'index']);
    Route::get('unassigned-node-errors/stats', [UnassignedNodeErrorController::class, 'stats']);
    Route::get('unassigned-node-errors/{hardwareId}', [UnassignedNodeErrorController::class, 'show']);
    Route::get('recipes', [RecipeController::class, 'index']);
    Route::get('recipes/{recipe}', [RecipeController::class, 'show']);
    Route::get('presets', [PresetController::class, 'index']);
    Route::get('presets/{preset}', [PresetController::class, 'show']);

    // Mutating endpoints (operator+)
    Route::middleware('role:operator,admin,agronomist,engineer')->group(function () {
        // Greenhouses
        Route::post('greenhouses', [GreenhouseController::class, 'store']);
        Route::put('greenhouses/{greenhouse}', [GreenhouseController::class, 'update']);
        Route::patch('greenhouses/{greenhouse}', [GreenhouseController::class, 'update']);
        Route::delete('greenhouses/{greenhouse}', [GreenhouseController::class, 'destroy']);

        // Zones
        Route::post('zones', [ZoneController::class, 'store']);
        Route::put('zones/{zone}', [ZoneController::class, 'update']);
        Route::patch('zones/{zone}', [ZoneController::class, 'update']);
        Route::delete('zones/{zone}', [ZoneController::class, 'destroy']);
        Route::post('zones/{zone}/attach-recipe', [ZoneController::class, 'attachRecipe']);
        Route::post('zones/{zone}/change-phase', [ZoneController::class, 'changePhase']);
        Route::post('zones/{zone}/next-phase', [ZoneController::class, 'nextPhase']);
        Route::post('zones/{zone}/pause', [ZoneController::class, 'pause']);
        Route::post('zones/{zone}/resume', [ZoneController::class, 'resume']);
        Route::post('zones/{zone}/fill', [ZoneController::class, 'fill']);
        Route::post('zones/{zone}/drain', [ZoneController::class, 'drain']);
        Route::post('zones/{zone}/calibrate-flow', [ZoneController::class, 'calibrateFlow']);

        // Nodes
        Route::post('nodes', [NodeController::class, 'store']);
        Route::put('nodes/{node}', [NodeController::class, 'update']);
        Route::patch('nodes/{node}', [NodeController::class, 'update'])
            ->middleware('verify.python.service');
        Route::delete('nodes/{node}', [NodeController::class, 'destroy']);
        Route::post('nodes/{node}/detach', [NodeController::class, 'detach']);
        Route::post('nodes/{node}/config/publish', [NodeController::class, 'publishConfig']);
        Route::post('nodes/{node}/swap', [NodeController::class, 'swap']);
        Route::post('nodes/{node}/lifecycle/transition', [NodeController::class, 'transitionLifecycle']);

        // Recipes
        Route::post('recipes', [RecipeController::class, 'store']);
        Route::put('recipes/{recipe}', [RecipeController::class, 'update']);
        Route::patch('recipes/{recipe}', [RecipeController::class, 'update']);
        Route::delete('recipes/{recipe}', [RecipeController::class, 'destroy']);
        Route::post('recipes/{recipe}/phases', [RecipePhaseController::class, 'store']);
        Route::patch('recipe-phases/{recipePhase}', [RecipePhaseController::class, 'update']);
        Route::delete('recipe-phases/{recipePhase}', [RecipePhaseController::class, 'destroy']);

        // Presets
        Route::post('presets', [PresetController::class, 'store']);
        Route::put('presets/{preset}', [PresetController::class, 'update']);
        Route::patch('presets/{preset}', [PresetController::class, 'update']);
        Route::delete('presets/{preset}', [PresetController::class, 'destroy']);

        // Commands (operator+)
        Route::post('zones/{zone}/commands', [ZoneCommandController::class, 'store']);
        Route::post('nodes/{node}/commands', [NodeCommandController::class, 'store']);

        // PID Config (operator+)
        Route::put('zones/{zone}/pid-configs/{type}', [ZonePidConfigController::class, 'update']);

        // Alerts (operator+)
        Route::patch('alerts/{alert}/ack', [AlertController::class, 'ack']);

        // AI endpoints (operator+)
        Route::post('ai/predict', [AiController::class, 'predict']);
        Route::post('ai/explain_zone', [AiController::class, 'explainZone']);
        Route::post('ai/recommend', [AiController::class, 'recommend']);
        Route::post('ai/diagnostics', [AiController::class, 'diagnostics']);

        // Simulations (operator+)
        Route::post('simulations/zone/{zone}', [SimulationController::class, 'simulateZone']);
        Route::post('zones/{zone}/simulate', [SimulationController::class, 'simulateZone']); // Alias for frontend compatibility

        // Profitability (operator+)
        Route::post('profitability/calculate', [ProfitabilityController::class, 'calculate']);
    });

    // PID Config read-only
    Route::get('zones/{zone}/pid-configs', [ZonePidConfigController::class, 'index']);
    Route::get('zones/{zone}/pid-configs/{type}', [ZonePidConfigController::class, 'show']);
    Route::get('zones/{zone}/pid-logs', [ZonePidLogController::class, 'index']);

    // Reports (viewer+)
    Route::get('recipes/{recipe}/analytics', [ReportController::class, 'recipeAnalytics']);
    Route::get('zones/{zone}/harvests', [ReportController::class, 'zoneHarvests']);
    Route::get('profitability/plants/{plant}', [ProfitabilityController::class, 'plant']);
    Route::middleware('role:operator,admin,agronomist,engineer')->group(function () {
        Route::post('harvests', [ReportController::class, 'storeHarvest']);
        Route::post('recipes/comparison', [ReportController::class, 'compareRecipes']);
    });

    // Telemetry (viewer+)
    Route::get('zones/{id}/telemetry/last', [TelemetryController::class, 'zoneLast']);
    Route::get('zones/{id}/telemetry/history', [TelemetryController::class, 'zoneHistory']);
    Route::get('nodes/{id}/telemetry/last', [TelemetryController::class, 'nodeLast']);
    Route::get('nodes/{id}/telemetry/history', [TelemetryController::class, 'nodeHistory']);
    Route::get('telemetry/aggregates', [TelemetryController::class, 'aggregates']);

    // Sync endpoints for WebSocket reconnection (viewer+)
    Route::get('sync/telemetry', [\App\Http\Controllers\SyncController::class, 'telemetry']);
    Route::get('sync/commands', [\App\Http\Controllers\SyncController::class, 'commands']);
    Route::get('sync/alerts', [\App\Http\Controllers\SyncController::class, 'alerts']);
    Route::get('sync/full', [\App\Http\Controllers\SyncController::class, 'full']);

    // Service logs (admin/operator/engineer)
    Route::middleware(['role:admin,operator,engineer', 'throttle:60,1'])
        ->get('logs/service', [ServiceLogController::class, 'index']);

    // Commands status (viewer+)
    Route::get('commands/{cmdId}/status', [\App\Http\Controllers\CommandStatusController::class, 'show']);

    // Alerts (viewer+)
    Route::get('alerts', [AlertController::class, 'index'])->middleware('throttle:120,1');
    Route::get('alerts/{alert}', [AlertController::class, 'show']);
    // SSE stream с ограничением подключений для предотвращения DoS (максимум 5 подключений на пользователя в минуту)
    Route::get('alerts/stream', [AlertStreamController::class, 'stream'])->middleware('throttle:5,1');

    // Simulations status (viewer+)
    Route::get('simulations/{jobId}', [SimulationController::class, 'show']);

    // Admin (минимальный CRUD поверх ресурсов): зоны быстрый create, рецепт быстрый update
    Route::middleware('role:admin')->prefix('admin')->group(function () {
        Route::post('zones/quick-create', [ZoneController::class, 'store']); // переиспользуем resource
        Route::patch('recipes/{recipe}/quick-update', [RecipeController::class, 'update']); // переиспользуем resource
    });

    // Users management (admin only)
    Route::middleware('role:admin')->apiResource('users', \App\Http\Controllers\UserController::class);
});

// Python ingest (token-based) - более высокий лимит для внутренних сервисов
Route::prefix('python')->middleware('throttle:120,1')->group(function () {
    Route::post('ingest/telemetry', [PythonIngestController::class, 'telemetry']);
    Route::post('commands/ack', [PythonIngestController::class, 'commandAck']);
    Route::post('broadcast/telemetry', [PythonIngestController::class, 'broadcastTelemetry']);
    Route::post('alerts', [PythonIngestController::class, 'alerts']);
    Route::post('logs', [ServiceLogController::class, 'store'])->middleware('verify.python.service');
});

// Node registration and service updates (token-based) - умеренный лимит
Route::middleware(['throttle:node_register', 'ip.whitelist'])->group(function () {
    Route::post('nodes/register', [NodeController::class, 'register']);
    
    // Node updates от сервисов (history-logger и т.д.) - проверка токена в контроллере
    Route::patch('nodes/{node}/service-update', [NodeController::class, 'update']);
    Route::post('nodes/{node}/lifecycle/service-transition', [NodeController::class, 'transitionLifecycle']);

    // Alertmanager webhook (защищен секретом)
    Route::post('alerts/webhook', [\App\Http\Controllers\Api\AlertWebhookController::class, 'webhook'])
        ->middleware('verify.alertmanager.webhook');
});
