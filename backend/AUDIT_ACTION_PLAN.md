# План действий по результатам аудита Backend

**Дата:** 8 декабря 2025  
**Статус:** К выполнению

---

## 🎯 Краткое резюме

Выявлено **3 критических** проблемы безопасности, **8 архитектурных** проблем и **15+** мест для улучшения качества кода.

**Рекомендуемая последовательность:**
1. Исправить критические проблемы безопасности (1-2 дня)
2. Рефакторинг архитектуры (1 неделя)
3. Улучшение качества кода (2 недели)

---

## 🔴 Критические исправления (День 1-2)

### 1. Удалить логирование токенов

**Файл:** `backend/laravel/app/Http/Controllers/NodeController.php:174-179`

**Было:**
```php
\Log::debug('[NodeController::update] Checking token', [
    'provided_token' => $providedToken ? substr($providedToken, 0, 10).'...' : 'null',
    'py_api_token' => config('services.python_bridge.token') ? 'set' : 'null',
    // ...
]);
```

**Стало:**
```php
Log::debug('NodeController: Authenticating service token');
```

---

### 2. Защита от SQL Injection в поиске

**Файл:** `backend/laravel/app/Http/Controllers/NodeController.php:95-100`

**Было:**
```php
if (isset($validated['search']) && $validated['search']) {
    $searchTerm = '%'.strtolower($validated['search']).'%';
    $query->where(function ($q) use ($searchTerm) {
        $q->whereRaw('LOWER(name) LIKE ?', [$searchTerm])
            ->orWhereRaw('LOWER(uid) LIKE ?', [$searchTerm])
            ->orWhereRaw('LOWER(type) LIKE ?', [$searchTerm]);
    });
}
```

**Стало:**
```php
if (isset($validated['search']) && $validated['search']) {
    $searchTerm = addcslashes($validated['search'], '%_');
    
    $query->where(function ($q) use ($searchTerm) {
        $q->where('name', 'ILIKE', "%{$searchTerm}%")
            ->orWhere('uid', 'ILIKE', "%{$searchTerm}%")
            ->orWhere('type', 'ILIKE', "%{$searchTerm}%");
    });
}
```

---

### 3. Защита config от утечки

**Файл:** `backend/laravel/app/Models/DeviceNode.php`

**Добавить:**
```php
protected $hidden = [
    'config', // Никогда не сериализуется в JSON
];
```

**Файл:** `backend/laravel/app/Models/NodeChannel.php`

**Добавить:**
```php
protected $hidden = [
    'config', // Никогда не сериализуется в JSON
];
```

---

### 4. Rate Limiting для регистрации нод

**Файл:** `backend/laravel/bootstrap/app.php`

**Добавить:**
```php
->withMiddleware(function (Middleware $middleware) {
    $middleware->throttleWithRedis();
    
    // Rate limiting для регистрации нод
    RateLimiter::for('node_register', function (Request $request) {
        return Limit::perMinute(10)->by($request->ip());
    });
})
```

**Файл:** `backend/laravel/routes/api.php`

**Изменить:**
```php
// Было:
Route::post('/nodes/register', [NodeController::class, 'register']);

// Стало:
Route::post('/nodes/register', [NodeController::class, 'register'])
    ->middleware('throttle:node_register');
```

---

### 5. Проверка безопасности в продакшене

**Создать файл:** `backend/laravel/app/Console/Commands/CheckSecurityConfig.php`

```php
<?php

namespace App\Console\Commands;

use Illuminate\Console\Command;

class CheckSecurityConfig extends Command
{
    protected $signature = 'security:check-config';
    protected $description = 'Check security configuration for production';

    public function handle(): int
    {
        if (!app()->isProduction()) {
            $this->info('Not in production, skipping security checks');
            return self::SUCCESS;
        }

        $errors = [];

        // Проверка токенов
        if (!config('services.python_bridge.token')) {
            $errors[] = 'PY_API_TOKEN not set';
        }

        if (!config('services.python_bridge.ingest_token')) {
            $errors[] = 'PY_INGEST_TOKEN not set';
        }

        if (!config('services.history_logger.token')) {
            $errors[] = 'HISTORY_LOGGER_TOKEN not set';
        }

        // Проверка DB password
        if (!config('database.connections.pgsql.password')) {
            $errors[] = 'DB_PASSWORD not set';
        }

        // Проверка MQTT password
        if (!config('services.mqtt.password')) {
            $errors[] = 'MQTT_PASSWORD not set';
        }

        // Проверка APP_KEY
        if (config('app.key') === 'base64:default_key' || empty(config('app.key'))) {
            $errors[] = 'APP_KEY is default or empty (insecure)';
        }

        if (!empty($errors)) {
            $this->error('Security configuration errors:');
            foreach ($errors as $error) {
                $this->error("  - {$error}");
            }
            return self::FAILURE;
        }

        $this->info('✓ Security configuration OK');
        return self::SUCCESS;
    }
}
```

**Добавить в CI/CD pipeline:**
```bash
# .github/workflows/tests.yml
- name: Check security config
  run: php artisan security:check-config
  env:
    APP_ENV: production
```

---

## 🟡 Архитектурный рефакторинг (Неделя 1)

### 6. Создать Middleware для сервисной аутентификации

**Создать файл:** `backend/laravel/app/Http/Middleware/AuthenticateServiceToken.php`

```php
<?php

namespace App\Http\Middleware;

use App\Models\User;
use Closure;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Log;

class AuthenticateServiceToken
{
    public function handle(Request $request, Closure $next): mixed
    {
        // Если уже авторизован через Sanctum
        if ($request->user()) {
            return $next($request);
        }

        $token = $request->bearerToken();
        if (!$token) {
            return response()->json(['message' => 'Unauthorized'], 401);
        }

        // Проверка токена
        $validTokens = array_filter([
            config('services.python_bridge.token'),
            config('services.python_bridge.ingest_token'),
            config('services.history_logger.token'),
        ]);

        foreach ($validTokens as $validToken) {
            if (hash_equals($validToken, $token)) {
                $serviceUser = $this->getServiceUser();
                
                if (!$serviceUser) {
                    Log::error('AuthenticateServiceToken: No service user found');
                    return response()->json(['message' => 'Service user not configured'], 500);
                }
                
                $request->setUserResolver(fn() => $serviceUser);
                
                Log::debug('AuthenticateServiceToken: Service authenticated');
                
                return $next($request);
            }
        }

        Log::warning('AuthenticateServiceToken: Invalid token', [
            'ip' => $request->ip(),
            'user_agent' => $request->userAgent(),
        ]);

        return response()->json(['message' => 'Unauthorized'], 401);
    }

    private function getServiceUser(): ?User
    {
        return User::whereIn('role', ['operator', 'admin'])
            ->orderBy('role', 'desc') // admin > operator
            ->first();
    }
}
```

**Зарегистрировать в `bootstrap/app.php`:**

```php
->withMiddleware(function (Middleware $middleware) {
    $middleware->alias([
        'auth.service' => \App\Http\Middleware\AuthenticateServiceToken::class,
    ]);
})
```

**Использовать в routes:**

```php
Route::middleware('auth.service')->group(function () {
    Route::put('/nodes/{node}', [NodeController::class, 'update']);
    Route::post('/telemetry/batch', [PythonIngestController::class, 'ingestBatch']);
});
```

---

### 7. Создать Form Request классы

#### StoreNodeCommandRequest

**Создать файл:** `backend/laravel/app/Http/Requests/StoreNodeCommandRequest.php`

```php
<?php

namespace App\Http\Requests;

use Illuminate\Foundation\Http\FormRequest;

class StoreNodeCommandRequest extends FormRequest
{
    public function authorize(): bool
    {
        return true; // Проверка через middleware/policy
    }

    public function rules(): array
    {
        return [
            'type' => ['nullable', 'string', 'max:64'],
            'cmd' => ['nullable', 'string', 'max:64'],
            'channel' => ['nullable', 'string', 'max:128'],
            'params' => ['nullable', 'array'],
            'params.*' => ['sometimes'],
        ];
    }

    public function messages(): array
    {
        return [
            'cmd.required' => 'The command field is required.',
            'cmd.max' => 'Command name cannot exceed 64 characters.',
            'channel.max' => 'Channel name cannot exceed 128 characters.',
            'params.array' => 'Parameters must be an associative array.',
        ];
    }

    public function passedValidation(): void
    {
        // Support both 'type' and 'cmd' fields for backward compatibility
        if (!$this->input('cmd') && $this->input('type')) {
            $this->merge(['cmd' => $this->input('type')]);
        }

        // Ensure cmd is set
        if (!$this->input('cmd')) {
            abort(422, 'The cmd or type field is required.');
        }

        // Ensure params is an associative array (object), not a list
        $params = $this->input('params', []);
        if (is_array($params) && array_is_list($params)) {
            $this->merge(['params' => []]);
        }

        // Для релейных команд set_state проставляем state по умолчанию
        if ($this->input('cmd') === 'set_state' && !isset($params['state'])) {
            $this->merge(['params' => array_merge($params, ['state' => 1])]);
        }
    }
}
```

**Использовать в контроллере:**

```php
// backend/laravel/app/Http/Controllers/NodeCommandController.php

public function store(
    StoreNodeCommandRequest $request,
    DeviceNode $node,
    PythonBridgeService $bridge
): JsonResponse {
    $data = $request->validated();

    try {
        $commandId = $bridge->sendNodeCommand($node, $data);

        return response()->json([
            'status' => 'ok',
            'data' => [
                'command_id' => $commandId,
            ],
        ]);
    } catch (ConnectionException $e) {
        // ... обработка ошибок ...
    }
}
```

#### Создать аналогичные Form Requests для:

- `StoreNodeRequest` (NodeController::store)
- `UpdateNodeRequest` (NodeController::update)
- `RegisterNodeRequest` (NodeController::register)
- `PublishNodeConfigRequest` (NodeController::publishConfig)

---

### 8. Создать Laravel Policies

**Создать файл:** `backend/laravel/app/Policies/DeviceNodePolicy.php`

```php
<?php

namespace App\Policies;

use App\Helpers\ZoneAccessHelper;
use App\Models\DeviceNode;
use App\Models\User;

class DeviceNodePolicy
{
    /**
     * Может ли пользователь просматривать ноду
     */
    public function view(User $user, DeviceNode $node): bool
    {
        return ZoneAccessHelper::canAccessNode($user, $node);
    }

    /**
     * Может ли пользователь обновлять ноду
     */
    public function update(User $user, DeviceNode $node): bool
    {
        return ZoneAccessHelper::canAccessNode($user, $node);
    }

    /**
     * Может ли пользователь удалять ноду
     */
    public function delete(User $user, DeviceNode $node): bool
    {
        return ZoneAccessHelper::canAccessNode($user, $node);
    }

    /**
     * Может ли пользователь отвязывать ноду от зоны
     */
    public function detach(User $user, DeviceNode $node): bool
    {
        return ZoneAccessHelper::canAccessNode($user, $node);
    }

    /**
     * Может ли пользователь публиковать конфиг ноды
     */
    public function publishConfig(User $user, DeviceNode $node): bool
    {
        return ZoneAccessHelper::canAccessNode($user, $node);
    }

    /**
     * Может ли пользователь отправлять команды ноде
     */
    public function sendCommand(User $user, DeviceNode $node): bool
    {
        return ZoneAccessHelper::canAccessNode($user, $node);
    }

    /**
     * Может ли пользователь переводить ноду в другое lifecycle состояние
     */
    public function transitionLifecycle(User $user, DeviceNode $node): bool
    {
        return $user->isAdmin() || ZoneAccessHelper::canAccessNode($user, $node);
    }
}
```

**Зарегистрировать в `app/Providers/AppServiceProvider.php` или `bootstrap/app.php`:**

```php
use Illuminate\Support\Facades\Gate;

Gate::policy(DeviceNode::class, DeviceNodePolicy::class);
```

**Использовать в контроллере:**

```php
public function show(Request $request, DeviceNode $node): JsonResponse
{
    $this->authorize('view', $node);
    
    $node->load([...]);

    return response()->json(['status' => 'ok', 'data' => $node]);
}

public function update(UpdateNodeRequest $request, DeviceNode $node): JsonResponse
{
    $this->authorize('update', $node);
    
    $data = $request->validated();
    
    // Проверяем доступ к новой зоне, если меняется
    if (isset($data['zone_id']) && $data['zone_id'] !== $node->zone_id) {
        if (!ZoneAccessHelper::canAccessZone($request->user(), $data['zone_id'])) {
            abort(403, 'Access denied to target zone');
        }
    }
    
    $node = $this->nodeService->update($node, $data);

    return response()->json(['status' => 'ok', 'data' => $node]);
}
```

---

### 9. Создать API Resources

**Создать файл:** `backend/laravel/app/Http/Resources/DeviceNodeResource.php`

```php
<?php

namespace App\Http\Resources;

use Illuminate\Http\Request;
use Illuminate\Http\Resources\Json\JsonResource;

class DeviceNodeResource extends JsonResource
{
    public function toArray(Request $request): array
    {
        return [
            'id' => $this->id,
            'uid' => $this->uid,
            'name' => $this->name,
            'type' => $this->type,
            'zone_id' => $this->zone_id,
            'status' => $this->status,
            'lifecycle_state' => $this->lifecycle_state?->value,
            'fw_version' => $this->fw_version,
            'hardware_revision' => $this->hardware_revision,
            'hardware_id' => $this->hardware_id,
            'validated' => $this->validated,
            'first_seen_at' => $this->first_seen_at,
            'created_at' => $this->created_at,
            'updated_at' => $this->updated_at,
            
            // Отношения
            'zone' => ZoneResource::make($this->whenLoaded('zone')),
            'channels' => NodeChannelResource::collection($this->whenLoaded('channels')),
            
            // config НИКОГДА не включается (защита Wi-Fi паролей и MQTT кредов)
        ];
    }
}
```

**Создать файл:** `backend/laravel/app/Http/Resources/NodeChannelResource.php`

```php
<?php

namespace App\Http\Resources;

use Illuminate\Http\Request;
use Illuminate\Http\Resources\Json\JsonResource;

class NodeChannelResource extends JsonResource
{
    public function toArray(Request $request): array
    {
        return [
            'id' => $this->id,
            'node_id' => $this->node_id,
            'channel' => $this->channel,
            'type' => $this->type,
            'metric' => $this->metric,
            'unit' => $this->unit,
            
            // config НИКОГДА не включается (защита параметров актуаторов)
        ];
    }
}
```

**Использовать в контроллере:**

```php
use App\Http\Resources\DeviceNodeResource;

public function index(Request $request): JsonResponse
{
    // ... фильтрация и пагинация ...
    
    return response()->json([
        'status' => 'ok',
        'data' => DeviceNodeResource::collection($items),
    ]);
}

public function show(Request $request, DeviceNode $node): JsonResponse
{
    $this->authorize('view', $node);
    
    $node->load(['zone', 'channels']);

    return response()->json([
        'status' => 'ok',
        'data' => DeviceNodeResource::make($node),
    ]);
}
```

---

### 10. Разбить большие методы

**Файл:** `backend/laravel/app/Http/Controllers/NodeController.php`

**Метод `update()` (сейчас 88 строк) — разбить на:**

```php
public function update(UpdateNodeRequest $request, DeviceNode $node): JsonResponse
{
    $this->authorize('update', $node);

    $data = $request->validated();
    
    $this->validateZoneChange($request->user(), $data, $node);
    
    $node = $this->nodeService->update($node, $data);

    return response()->json(['status' => 'ok', 'data' => DeviceNodeResource::make($node)]);
}

/**
 * Валидирует изменение зоны (если zone_id меняется)
 */
private function validateZoneChange(User $user, array $data, DeviceNode $node): void
{
    if (isset($data['zone_id']) && $data['zone_id'] !== $node->zone_id) {
        if (!ZoneAccessHelper::canAccessZone($user, $data['zone_id'])) {
            abort(403, 'Access denied to target zone');
        }
    }
}
```

**Метод `publishConfig()` (сейчас 244 строки) — разбить на:**

```php
public function publishConfig(
    DeviceNode $node,
    PublishNodeConfigRequest $request
): JsonResponse {
    $this->authorize('publishConfig', $node);

    $config = $this->configService->generateNodeConfig($node, null, true);
    
    $this->validateNodeAssignment($node);
    
    $response = $this->publishConfigToMqtt($node, $config);

    return response()->json([
        'status' => 'ok',
        'data' => [
            'node' => DeviceNodeResource::make($node->fresh(['channels'])),
            'published_config' => $config,
            'bridge_response' => $response,
        ],
    ]);
}

private function validateNodeAssignment(DeviceNode $node): void
{
    if (!$node->zone_id) {
        abort(400, 'Node must be assigned to a zone before publishing config');
    }

    $node->load('zone.greenhouse');
    
    if (!$node->zone?->greenhouse?->uid) {
        abort(400, 'Zone must have a greenhouse before publishing config');
    }
}

private function publishConfigToMqtt(DeviceNode $node, array $config): array
{
    $baseUrl = config('services.history_logger.url');
    $token = config('services.history_logger.token') ?? config('services.python_bridge.token');

    if (!$baseUrl) {
        throw new \RuntimeException('History Logger URL not configured');
    }

    $headers = $token ? ['Authorization' => "Bearer {$token}"] : [];

    $response = Http::withHeaders($headers)
        ->timeout(10)
        ->post("{$baseUrl}/nodes/{$node->uid}/config", [
            'node_uid' => $node->uid,
            'zone_id' => $node->zone_id,
            'greenhouse_uid' => $node->zone->greenhouse->uid,
            'config' => $config,
            'hardware_id' => $node->hardware_id,
        ]);

    if (!$response->successful()) {
        Log::warning('Failed to publish config via MQTT', [
            'node_id' => $node->id,
            'status' => $response->status(),
        ]);
        
        abort($response->status(), 'Failed to publish config via MQTT bridge');
    }

    return $response->json();
}
```

---

## 🟢 Улучшения качества (Недели 2-3)

### 11. Добавить тесты для новых компонентов

**Создать файл:** `backend/laravel/tests/Feature/NodeControllerTest.php`

```php
<?php

namespace Tests\Feature;

use App\Models\DeviceNode;
use App\Models\User;
use App\Models\Zone;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class NodeControllerTest extends TestCase
{
    use RefreshDatabase;

    public function test_user_can_view_accessible_nodes(): void
    {
        $user = User::factory()->create(['role' => 'operator']);
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create(['zone_id' => $zone->id]);

        $response = $this->actingAs($user)->getJson("/api/nodes/{$node->id}");

        $response->assertOk()
            ->assertJson([
                'status' => 'ok',
                'data' => [
                    'id' => $node->id,
                    'uid' => $node->uid,
                ],
            ])
            ->assertJsonMissing(['config']);
    }

    public function test_config_is_never_exposed(): void
    {
        $user = User::factory()->create(['role' => 'admin']);
        $node = DeviceNode::factory()->create([
            'config' => ['wifi' => ['password' => 'secret123']],
        ]);

        $response = $this->actingAs($user)->getJson("/api/nodes/{$node->id}");

        $response->assertOk()
            ->assertJsonMissing(['config'])
            ->assertJsonMissing(['secret123']);
    }

    public function test_service_token_can_access_nodes(): void
    {
        $node = DeviceNode::factory()->create();
        $token = config('services.python_bridge.token');

        $response = $this->withToken($token)->getJson("/api/nodes/{$node->id}");

        $response->assertOk();
    }
}
```

---

## 📊 Метрики прогресса

После завершения всех исправлений:

| Метрика | Было | Станет |
|---------|------|--------|
| Критические проблемы безопасности | 3 | 0 |
| Архитектурные проблемы | 8 | 0 |
| Form Request классы | 0% | 100% |
| API Resources | 0% | 100% |
| Policies | 0% | 100% |
| Контроллеры >100 строк | 5 | 0 |
| Test Coverage | 60% | 80% |
| **Общая оценка** | 7.5/10 | 9.0/10 |

---

## 🎓 Обучающие материалы

### Laravel Best Practices

- [Laravel Policies](https://laravel.com/docs/12.x/authorization#creating-policies)
- [Form Request Validation](https://laravel.com/docs/12.x/validation#form-request-validation)
- [API Resources](https://laravel.com/docs/12.x/eloquent-resources)
- [Middleware](https://laravel.com/docs/12.x/middleware)
- [Rate Limiting](https://laravel.com/docs/12.x/routing#rate-limiting)

### Security

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Laravel Security Best Practices](https://laravel.com/docs/12.x/security)
- [SQL Injection Prevention](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html)

---

## ✅ Чек-лист выполнения

### День 1-2: Критические исправления

- [ ] Удалить логирование токенов
- [ ] Исправить SQL Injection в поиске
- [ ] Добавить $hidden для config
- [ ] Добавить Rate Limiting
- [ ] Создать команду проверки безопасности
- [ ] Добавить проверку в CI/CD

### Неделя 1: Архитектурный рефакторинг

- [ ] Создать Middleware `AuthenticateServiceToken`
- [ ] Создать Form Request: `StoreNodeCommandRequest`
- [ ] Создать Form Request: `StoreNodeRequest`
- [ ] Создать Form Request: `UpdateNodeRequest`
- [ ] Создать Form Request: `RegisterNodeRequest`
- [ ] Создать Form Request: `PublishNodeConfigRequest`
- [ ] Создать Policy: `DeviceNodePolicy`
- [ ] Создать Resource: `DeviceNodeResource`
- [ ] Создать Resource: `NodeChannelResource`
- [ ] Разбить метод `NodeController::update()`
- [ ] Разбить метод `NodeController::publishConfig()`

### Недели 2-3: Качество и тесты

- [ ] Добавить unit-тесты для Policies
- [ ] Добавить feature-тесты для контроллеров
- [ ] Добавить тесты для Form Requests
- [ ] Добавить type hints везде
- [ ] Исправить все TODO комментарии
- [ ] Обновить документацию

---

**Следующий шаг:** Начать с критических исправлений (День 1-2)

**Контакт для вопросов:** См. полный отчет в `AUDIT_REPORT.md`
