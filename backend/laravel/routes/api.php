<?php

use App\Http\Controllers\AiController;
use App\Http\Controllers\AlertController;
use App\Http\Controllers\AlertStreamController;
use App\Http\Controllers\AuthController;
use App\Http\Controllers\E2EAuthController;
use App\Http\Controllers\GreenhouseController;
use App\Http\Controllers\NodeCommandController;
use App\Http\Controllers\NodeController;
use App\Http\Controllers\PresetController;
use App\Http\Controllers\ProfitabilityController;
use App\Http\Controllers\PythonIngestController;
use App\Http\Controllers\RecipeController;
use App\Http\Controllers\ReportController;
use App\Http\Controllers\ServiceLogController;
use App\Http\Controllers\SimulationController;
use App\Http\Controllers\SystemController;
use App\Http\Controllers\TelemetryController;
use App\Http\Controllers\ZoneCommandController;
use App\Http\Controllers\ZoneController;
use App\Http\Controllers\ZonePidConfigController;
use App\Http\Controllers\ZonePidLogController;
use App\Http\Controllers\ZoneInfrastructureController;
use App\Http\Controllers\UnassignedNodeErrorController;
use App\Http\Controllers\PipelineHealthController;
use App\Http\Controllers\GrowCycleController;
use App\Http\Controllers\PlantController;
use App\Http\Controllers\RecipeRevisionController;
use App\Http\Controllers\RecipeRevisionPhaseController;
use App\Http\Controllers\InfrastructureInstanceController;
use App\Http\Controllers\ChannelBindingController;
use Illuminate\Support\Facades\Route;
use Illuminate\Http\Request;

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

// E2E Auth Bootstrap endpoint - создание пользователя и токена для E2E тестов
// Проверка окружения выполняется в контроллере
Route::post('e2e/auth/token', [E2EAuthController::class, 'createToken'])
    ->middleware('throttle:10,1');

// Debug endpoint for E2E: verify that Authorization header reaches PHP/Laravel through nginx/FastCGI.
// Only enabled in testing environment.
if (app()->environment('testing', 'e2e')) {
    Route::get('system/auth-debug', function (Request $request) {
        $bearer = $request->bearerToken();
        $authHeader = $request->header('Authorization');
        $serverAuth = $request->server('HTTP_AUTHORIZATION');
        $serverRedirectAuth = $request->server('REDIRECT_HTTP_AUTHORIZATION');

        return response()->json([
            'status' => 'ok',
            'data' => [
                'has_authorization_header' => $request->headers->has('Authorization'),
                'authorization_header_prefix' => is_string($authHeader) ? substr($authHeader, 0, 20) : null,
                'bearer_token_prefix' => is_string($bearer) ? substr($bearer, 0, 12) : null,
                'server_http_authorization_prefix' => is_string($serverAuth) ? substr($serverAuth, 0, 20) : null,
                'server_redirect_http_authorization_prefix' => is_string($serverRedirectAuth) ? substr($serverRedirectAuth, 0, 20) : null,
            ],
        ]);
    })->middleware([
        \Illuminate\Cookie\Middleware\EncryptCookies::class,
        \Illuminate\Session\Middleware\StartSession::class,
        \App\Http\Middleware\AuthenticateWithApiToken::class,
        'throttle:60,1',
    ]);
}
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
    // API routes should accept Sanctum bearer tokens (E2E / services) and also work for session-auth SPA if needed.
    'auth:sanctum',
    'throttle:120,1', // Увеличен лимит до 120 запросов в минуту для поддержки множественных компонентов
])->group(function () {
    // Read-only endpoints (viewer+)
    Route::get('greenhouses', [GreenhouseController::class, 'index']);
    Route::get('greenhouses/{greenhouse}', [GreenhouseController::class, 'show']);
    Route::get('greenhouses/{greenhouse}/dashboard', [GreenhouseController::class, 'dashboard']);
    Route::get('zones', [ZoneController::class, 'index']);
    Route::get('zones/{zone}', [ZoneController::class, 'show']);
    Route::get('zones/{zone}/health', [ZoneController::class, 'health']);
    Route::get('zones/{zone}/cycles', [ZoneController::class, 'cycles']);
    Route::get('zones/{zone}/unassigned-errors', [ZoneController::class, 'unassignedErrors']);
    Route::get('zones/{zone}/events', [ZoneController::class, 'events']);
    Route::get('zones/{zone}/snapshot', [ZoneController::class, 'snapshot']);
    Route::get('zones/{zone}/infrastructure', [ZoneInfrastructureController::class, 'show']);
    Route::get('zones/{zone}/grow-cycle', [GrowCycleController::class, 'getActive']);
    Route::get('greenhouses/{greenhouse}/grow-cycles', [GrowCycleController::class, 'indexByGreenhouse']);
    
    // Recipe revisions
    Route::get('recipe-revisions/{recipeRevision}', [RecipeRevisionController::class, 'show']);
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
    Route::get('plants', [PlantController::class, 'index']);
    Route::post('plants', [PlantController::class, 'store']);
    Route::get('plants/{plant}', [PlantController::class, 'show']);
    Route::put('plants/{plant}', [PlantController::class, 'update']);
    Route::delete('plants/{plant}', [PlantController::class, 'destroy']);
    
    // Grow Cycle Wizard endpoints
    Route::get('grow-cycle-wizard/data', [\App\Http\Controllers\GrowCycleWizardController::class, 'getWizardData']);
    Route::get('grow-cycle-wizard/zone/{zone}', [\App\Http\Controllers\GrowCycleWizardController::class, 'getZoneData']);

    // Mutating endpoints (operator+)
    Route::middleware(['role:operator,admin,agronomist,engineer', 'ae.legacy.sql.guard'])->group(function () {
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
        // Infrastructure instances
        Route::get('zones/{zone}/infrastructure-instances', [InfrastructureInstanceController::class, 'indexForZone']);
        Route::get('greenhouses/{greenhouse}/infrastructure-instances', [InfrastructureInstanceController::class, 'indexForGreenhouse']);
        Route::post('infrastructure-instances', [InfrastructureInstanceController::class, 'store']);
        Route::patch('infrastructure-instances/{infrastructureInstance}', [InfrastructureInstanceController::class, 'update']);
        Route::delete('infrastructure-instances/{infrastructureInstance}', [InfrastructureInstanceController::class, 'destroy']);
        
        // Channel bindings
        Route::post('channel-bindings', [ChannelBindingController::class, 'store']);
        Route::patch('channel-bindings/{channelBinding}', [ChannelBindingController::class, 'update']);
        Route::delete('channel-bindings/{channelBinding}', [ChannelBindingController::class, 'destroy']);
        
        Route::post('zones/{zone}/fill', [ZoneController::class, 'fill']);
        Route::post('zones/{zone}/drain', [ZoneController::class, 'drain']);
        Route::post('zones/{zone}/calibrate-flow', [ZoneController::class, 'calibrateFlow']);
        Route::put('zones/{zone}/infrastructure', [ZoneInfrastructureController::class, 'update']);
        Route::post('zones/{zone}/infrastructure/bindings', [ZoneInfrastructureController::class, 'storeBinding']);
        Route::delete('zones/{zone}/infrastructure/bindings/{zoneChannelBinding}', [ZoneInfrastructureController::class, 'destroyBinding']);

        // Grow Cycle operations
        Route::get('grow-cycles', [GrowCycleController::class, 'index']);
        Route::post('zones/{zone}/grow-cycles', [GrowCycleController::class, 'store']);
        Route::post('grow-cycles/{growCycle}/start', [GrowCycleController::class, 'start']);
        Route::post('grow-cycles/{growCycle}/pause', [GrowCycleController::class, 'pause']);
        Route::post('grow-cycles/{growCycle}/resume', [GrowCycleController::class, 'resume']);
        Route::post('grow-cycles/{growCycle}/harvest', [GrowCycleController::class, 'harvest']);
        Route::post('grow-cycles/{growCycle}/abort', [GrowCycleController::class, 'abort']);
        Route::post('grow-cycles/{growCycle}/set-phase', [GrowCycleController::class, 'setPhase']);
        Route::post('grow-cycles/{growCycle}/advance-phase', [GrowCycleController::class, 'advancePhase']);
        Route::post('grow-cycles/{growCycle}/change-recipe-revision', [GrowCycleController::class, 'changeRecipeRevision']);
        


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
        
        // Recipe revisions
        Route::post('recipes/{recipe}/revisions', [RecipeRevisionController::class, 'store']);
        Route::patch('recipe-revisions/{recipeRevision}', [RecipeRevisionController::class, 'update']);
        Route::post('recipe-revisions/{recipeRevision}/publish', [RecipeRevisionController::class, 'publish']);
        
        // Recipe revision phases
        Route::post('recipe-revisions/{recipeRevision}/phases', [RecipeRevisionPhaseController::class, 'store']);
        Route::patch('recipe-revision-phases/{recipeRevisionPhase}', [RecipeRevisionPhaseController::class, 'update']);
        Route::delete('recipe-revision-phases/{recipeRevisionPhase}', [RecipeRevisionPhaseController::class, 'destroy']);

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
        Route::post('alerts/dlq/{id}/replay', [AlertController::class, 'replayDlq']);
        
        // Grow Cycle Wizard (operator+)
        Route::post('grow-cycle-wizard/create', [\App\Http\Controllers\GrowCycleWizardController::class, 'createGrowCycle']);

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
    
    // Pipeline Health (viewer+)
    Route::get('pipeline/health', [PipelineHealthController::class, 'pipelineHealth']);

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

// Internal API для Python сервисов (требует verify.python.service middleware)
Route::prefix('internal')->middleware(['verify.python.service', 'throttle:120,1'])->group(function () {
    Route::post('effective-targets/batch', [\App\Http\Controllers\InternalApiController::class, 'getEffectiveTargetsBatch']);
});

// Node registration and service updates (token-based) - умеренный лимит
Route::middleware(['throttle:node_register', 'ip.whitelist'])->group(function () {
    Route::post('nodes/register', [NodeController::class, 'register']);
    
    // Node updates от сервисов (history-logger и т.д.) - проверка токена в контроллере
    Route::patch('nodes/{node}/service-update', [NodeController::class, 'serviceUpdate']);
    Route::post('nodes/{node}/lifecycle/service-transition', [NodeController::class, 'transitionLifecycle']);

    // Alertmanager webhook (защищен секретом)
    Route::post('alerts/webhook', [\App\Http\Controllers\Api\AlertWebhookController::class, 'webhook'])
        ->middleware('verify.alertmanager.webhook');
});
