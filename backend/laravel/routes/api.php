<?php

use Illuminate\Support\Facades\Route;
use App\Http\Controllers\AuthController;
use App\Http\Controllers\GreenhouseController;
use App\Http\Controllers\ZoneController;
use App\Http\Controllers\NodeController;
use App\Http\Controllers\TelemetryController;
use App\Http\Controllers\RecipeController;
use App\Http\Controllers\RecipePhaseController;
use App\Http\Controllers\PresetController;
use App\Http\Controllers\ReportController;
use App\Http\Controllers\ZoneCommandController;
use App\Http\Controllers\NodeCommandController;
use App\Http\Controllers\SystemController;
use App\Http\Controllers\AlertController;
use App\Http\Controllers\AlertStreamController;
use App\Http\Controllers\PythonIngestController;
use App\Http\Controllers\AiController;
use App\Http\Controllers\SimulationController;

// Auth роуты с более строгим rate limiting для предотвращения брутфорса
Route::prefix('auth')->middleware('throttle:10,1')->group(function () {
    Route::post('/login', [AuthController::class, 'login']);
    Route::post('/logout', [AuthController::class, 'logout'])->middleware('auth:sanctum');
    Route::get('/me', [AuthController::class, 'me'])->middleware('auth:sanctum');
});

// Публичные системные эндпоинты с умеренным rate limiting
Route::middleware('throttle:30,1')->group(function () {
    Route::get('system/health', [SystemController::class, 'health']);
    // configFull требует авторизации для защиты конфигурации системы
    Route::get('system/config/full', [SystemController::class, 'configFull'])->middleware('auth:sanctum');
});

// API routes for Inertia (using session authentication)
// Note: Session middleware is added here for routes that use session-based auth
// EncryptCookies must come before StartSession
// Rate limiting: 60 requests per minute (default from bootstrap/app.php)
Route::middleware([
    \Illuminate\Cookie\Middleware\EncryptCookies::class,
    \Illuminate\Session\Middleware\StartSession::class,
    'auth',
    'throttle:60,1', // Явно указываем rate limiting для этой группы
])->group(function () {
    Route::apiResource('greenhouses', GreenhouseController::class);
    Route::apiResource('zones', ZoneController::class);
    Route::apiResource('nodes', NodeController::class);
    Route::apiResource('recipes', RecipeController::class);
    Route::post('recipes/{recipe}/phases', [RecipePhaseController::class, 'store']);
    Route::patch('recipe-phases/{recipePhase}', [RecipePhaseController::class, 'update']);
    Route::delete('recipe-phases/{recipePhase}', [RecipePhaseController::class, 'destroy']);

    // Presets
    Route::apiResource('presets', PresetController::class);

    // Reports
    Route::get('recipes/{recipe}/analytics', [ReportController::class, 'recipeAnalytics']);
    Route::get('zones/{zone}/harvests', [ReportController::class, 'zoneHarvests']);
    Route::post('harvests', [ReportController::class, 'storeHarvest']);
    Route::post('recipes/comparison', [ReportController::class, 'compareRecipes']);

    // Telemetry
    Route::get('zones/{id}/telemetry/last', [TelemetryController::class, 'zoneLast']);
    Route::get('zones/{id}/telemetry/history', [TelemetryController::class, 'zoneHistory']);
    Route::get('nodes/{id}/telemetry/last', [TelemetryController::class, 'nodeLast']);
    Route::get('telemetry/aggregates', [TelemetryController::class, 'aggregates']);

    // Recipes attach/change-phase
    Route::post('zones/{zone}/attach-recipe', [ZoneController::class, 'attachRecipe']);
    Route::post('zones/{zone}/change-phase', [ZoneController::class, 'changePhase']);
    Route::post('zones/{zone}/next-phase', [ZoneController::class, 'nextPhase']);
    Route::post('zones/{zone}/pause', [ZoneController::class, 'pause']);
    Route::post('zones/{zone}/resume', [ZoneController::class, 'resume']);
    Route::get('zones/{zone}/health', [ZoneController::class, 'health']);
    Route::get('zones/{zone}/cycles', [ZoneController::class, 'cycles']);
    Route::post('zones/{zone}/fill', [ZoneController::class, 'fill']);
    Route::post('zones/{zone}/drain', [ZoneController::class, 'drain']);
    Route::post('zones/{zone}/calibrate-flow', [ZoneController::class, 'calibrateFlow']);
    
    // Digital Twin simulation
    Route::post('zones/{zone}/simulate', [SimulationController::class, 'simulateZone']);

    // Commands
    Route::post('zones/{zone}/commands', [ZoneCommandController::class, 'store']);
    Route::post('nodes/{node}/commands', [NodeCommandController::class, 'store']);
    Route::get('nodes/{node}/config', [NodeController::class, 'getConfig']);
    Route::post('nodes/{node}/config/publish', [NodeController::class, 'publishConfig']);
    Route::post('nodes/{node}/swap', [NodeController::class, 'swap']);
    Route::get('commands/{cmdId}/status', [\App\Http\Controllers\CommandStatusController::class, 'show']);

    // Alerts
    Route::get('alerts', [AlertController::class, 'index']);
    Route::get('alerts/{alert}', [AlertController::class, 'show']);
    Route::patch('alerts/{alert}/ack', [AlertController::class, 'ack']);
    Route::get('alerts/stream', [AlertStreamController::class, 'stream']);

    // AI endpoints
    Route::post('ai/predict', [AiController::class, 'predict']);
    Route::post('ai/explain_zone', [AiController::class, 'explainZone']);
    Route::post('ai/recommend', [AiController::class, 'recommend']);
    Route::post('ai/diagnostics', [AiController::class, 'diagnostics']);

    // Simulations (Digital Twin)
    Route::post('simulations/zone/{zone}', [SimulationController::class, 'simulateZone']);
    Route::get('simulations/{simulation}', [SimulationController::class, 'show']);

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
});

// Node registration (token-based or public) - умеренный лимит
Route::middleware('throttle:20,1')->group(function () {
    Route::post('nodes/register', [NodeController::class, 'register']);
    
    // Alertmanager webhook (публичный, но можно добавить токен)
    Route::post('alerts/webhook', [\App\Http\Controllers\Api\AlertWebhookController::class, 'webhook']);
});


