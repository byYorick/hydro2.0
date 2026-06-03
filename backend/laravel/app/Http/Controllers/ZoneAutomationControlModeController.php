<?php

namespace App\Http\Controllers;

use App\Http\Controllers\Concerns\PresentsLocalizedApiErrors;
use App\Helpers\ZoneAccessHelper;
use App\Models\Zone;
use App\Services\AutomationRuntimeConfigService;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Http\Client\RequestException;
use Illuminate\Http\Client\Response;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;

class ZoneAutomationControlModeController extends Controller
{
    use PresentsLocalizedApiErrors;

    public function __construct(
        private readonly AutomationRuntimeConfigService $runtimeConfig,
    ) {}

    public function show(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request, $zone);

        try {
            $payload = $this->fetchFromAutomationEngine($zone->id);
        } catch (RequestException $e) {
            $proxyResponse = $this->buildAutomationEngineErrorResponse(
                $e,
                'Automation-engine ещё не поддерживает control-mode API.',
            );
            if ($proxyResponse instanceof JsonResponse) {
                return $proxyResponse;
            }

            Log::warning('ZoneAutomationControlModeController: automation-engine unavailable', [
                'zone_id' => $zone->id,
                'error' => $e->getMessage(),
            ]);

            return $this->localizedError('upstream_unavailable', null, 503);
        } catch (ConnectionException $e) {
            Log::warning('ZoneAutomationControlModeController: automation-engine unavailable', [
                'zone_id' => $zone->id,
                'error' => $e->getMessage(),
            ]);

            return $this->localizedError('upstream_unavailable', null, 503);
        } catch (\Throwable $e) {
            Log::warning('ZoneAutomationControlModeController: unexpected upstream error', [
                'zone_id' => $zone->id,
                'error' => $e->getMessage(),
            ]);

            return $this->localizedError('upstream_error', 'Ошибка при получении control mode.', 503);
        }

        return response()->json($payload);
    }

    public function update(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request, $zone);

        $validated = $request->validate([
            'control_mode' => ['required', 'string', 'in:auto,semi,manual'],
            'source' => ['nullable', 'string', 'max:64'],
            'reason' => ['nullable', 'string', 'max:500'],
        ]);

        $user = $request->user();
        $userRole = $this->resolveUserRole($user);
        $newMode = $validated['control_mode'];
        $currentMode = strtolower(trim((string) ($zone->control_mode ?? 'auto')));

        if (! $this->isTransitionAllowedForRole($userRole, $currentMode, $newMode)) {
            return $this->localizedError(
                'control_mode_forbidden_for_role',
                'Текущая роль не разрешает переключение control_mode в этом направлении.',
                403,
                [
                    'details' => [
                        'role' => $userRole,
                        'from' => $currentMode,
                        'to' => $newMode,
                    ],
                ],
            );
        }

        if ($userRole === 'operator' && $newMode === 'manual'
            && empty(trim((string) ($validated['reason'] ?? '')))) {
            return $this->localizedError(
                'reason_required_for_operator_emergency',
                'Оператор обязан указать reason при аварийном переходе в manual.',
                422,
            );
        }

        $payload = [
            'control_mode' => $newMode,
            'source' => $validated['source'] ?? 'frontend',
            'user_id' => $user?->id,
            'user_role' => $userRole,
            'reason' => $validated['reason'] ?? null,
        ];

        try {
            $upstreamPayload = $this->updateInAutomationEngine($zone->id, $payload);
        } catch (RequestException $e) {
            $proxyResponse = $this->buildAutomationEngineErrorResponse(
                $e,
                'Automation-engine ещё не поддерживает control-mode API.',
            );
            if ($proxyResponse instanceof JsonResponse) {
                return $proxyResponse;
            }

            Log::warning('ZoneAutomationControlModeController: automation-engine unavailable', [
                'zone_id' => $zone->id,
                'error' => $e->getMessage(),
            ]);

            return $this->localizedError('upstream_unavailable', null, 503);
        } catch (ConnectionException $e) {
            Log::warning('ZoneAutomationControlModeController: automation-engine unavailable', [
                'zone_id' => $zone->id,
                'error' => $e->getMessage(),
            ]);

            return $this->localizedError('upstream_unavailable', null, 503);
        } catch (\Throwable $e) {
            Log::warning('ZoneAutomationControlModeController: unexpected upstream error', [
                'zone_id' => $zone->id,
                'error' => $e->getMessage(),
            ]);

            return $this->localizedError('upstream_error', 'Ошибка при обновлении control mode.', 503);
        }

        ZoneAutomationStateController::invalidateZoneStateCache($zone->id);
        Cache::forget("zone_automation_state:control_mode_backoff:{$zone->id}");
        $zone->refresh();

        return response()->json($upstreamPayload);
    }

    private function authorizeZoneAccess(Request $request, Zone $zone): void
    {
        $user = $request->user();
        if (! $user) {
            abort(401, 'Unauthorized');
        }

        if (! ZoneAccessHelper::canAccessZone($user, $zone)) {
            abort(403, 'Forbidden: Access denied to this zone');
        }
    }

    /**
     * Матрица переходов по ролям из CONTROL_MODES_SPEC.md §8.1:
     * - Agronomist / Engineer / Admin — любые переходы.
     * - Operator — только emergency `auto|semi → manual`.
     * - Viewer — запрещено.
     */
    private function isTransitionAllowedForRole(string $role, string $fromMode, string $toMode): bool
    {
        $role = strtolower(trim($role));
        if ($fromMode === $toMode) {
            return true; // no-op; handled downstream (will be short-circuited)
        }

        $unrestrictedRoles = ['agronomist', 'engineer', 'admin'];
        if (in_array($role, $unrestrictedRoles, true)) {
            return true;
        }

        if ($role === 'operator') {
            return in_array($fromMode, ['auto', 'semi'], true) && $toMode === 'manual';
        }

        return false; // viewer, unknown
    }

    private function resolveUserRole(?\App\Models\User $user): string
    {
        if (! $user) {
            return '';
        }
        $role = strtolower(trim((string) ($user->role ?? '')));

        return $role !== '' ? $role : 'agronomist';
    }

    /**
     * @return array<string,mixed>
     */
    private function fetchFromAutomationEngine(int $zoneId): array
    {
        $cfg = $this->runtimeConfig->schedulerConfig();
        $apiUrl = (string) ($cfg['api_url'] ?? 'http://automation-engine:9405');
        $timeout = (float) ($cfg['timeout_sec'] ?? 2.0);

        /** @var Response $response */
        $response = Http::acceptJson()
            ->timeout($timeout)
            ->withHeaders($this->automationEngineHeaders())
            ->get("{$apiUrl}/zones/{$zoneId}/control-mode");

        $response->throw();

        $decoded = $response->json();
        if (! is_array($decoded)) {
            throw new \RuntimeException('automation_engine_invalid_payload');
        }

        return $decoded;
    }

    /**
     * @param  array<string,mixed>  $payload
     * @return array<string,mixed>
     */
    private function updateInAutomationEngine(int $zoneId, array $payload): array
    {
        $cfg = $this->runtimeConfig->schedulerConfig();
        $apiUrl = (string) ($cfg['api_url'] ?? 'http://automation-engine:9405');
        $timeout = (float) ($cfg['timeout_sec'] ?? 2.0);

        /** @var Response $response */
        $response = Http::acceptJson()
            ->timeout($timeout)
            ->withHeaders($this->automationEngineHeaders())
            ->post("{$apiUrl}/zones/{$zoneId}/control-mode", $payload);

        $response->throw();

        $decoded = $response->json();
        if (! is_array($decoded)) {
            throw new \RuntimeException('automation_engine_invalid_payload');
        }

        return $decoded;
    }

    /**
     * @return array<string,string>
     */
    private function automationEngineHeaders(): array
    {
        $cfg = $this->runtimeConfig->schedulerConfig();

        $headers = [
            'X-Trace-Id' => Str::lower((string) Str::uuid()),
            'X-Scheduler-Id' => (string) ($cfg['scheduler_id'] ?? 'laravel-api'),
        ];

        $token = trim((string) ($cfg['token'] ?? ''));
        if ($token !== '') {
            $headers['Authorization'] = 'Bearer '.$token;
        }

        return $headers;
    }
}
