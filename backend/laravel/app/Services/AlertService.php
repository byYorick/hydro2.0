<?php

namespace App\Services;

use App\Models\Alert;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

class AlertService
{
    private AlertCatalogService $alertCatalog;

    public function __construct(?AlertCatalogService $alertCatalog = null)
    {
        $this->alertCatalog = $alertCatalog ?? app(AlertCatalogService::class);
    }

    /**
     * Создать алерт.
     * При ошибке сохраняет в pending_alerts для последующей обработки через DLQ.
     */
    public function create(array $data): Alert
    {
        $prepared = $this->prepareAlertPayload($data);

        try {
            return DB::transaction(function () use ($prepared) {
                $alert = Alert::create([
                    'zone_id' => $prepared['zone_id'],
                    'source' => $prepared['source'],
                    'code' => $prepared['code'],
                    'type' => $prepared['type'],
                    'status' => $this->normalizeStatus($prepared['status'] ?? 'ACTIVE'),
                    'category' => $prepared['category'],
                    'severity' => $prepared['severity'],
                    'node_uid' => $prepared['node_uid'],
                    'hardware_id' => $prepared['hardware_id'],
                    'details' => $prepared['details'],
                    'error_count' => (int) ($prepared['error_count'] ?? 1),
                    'first_seen_at' => $prepared['first_seen_at'] ?? now(),
                    'last_seen_at' => $prepared['last_seen_at'] ?? now(),
                    'created_at' => $prepared['created_at'] ?? now(),
                    'resolved_at' => $prepared['resolved_at'] ?? null,
                ]);

                Log::info('Alert created', [
                    'alert_id' => $alert->id,
                    'code' => $alert->code,
                    'source' => $alert->source,
                    'zone_id' => $alert->zone_id,
                ]);

                DB::afterCommit(function () use ($alert) {
                    $this->broadcastAlertCreated($alert);
                });

                return $alert;
            });
        } catch (\Exception $e) {
            $this->saveToPendingAlerts($prepared, $e);
            throw $e;
        }
    }

    /**
     * Создать или обновить активный алерт с дедупликацией.
     *
     * @param array<string, mixed> $data
     * @return array{alert: Alert|null, created: bool, event_id: int|null, rate_limited?: bool}
     */
    public function createOrUpdateActive(array $data): array
    {
        $prepared = $this->prepareAlertPayload($data);
        $zoneId = $prepared['zone_id'];
        $code = $prepared['code'];

        if ($code === '' || $code === 'unknown_alert') {
            throw new \InvalidArgumentException('code is required for deduplication');
        }

        return DB::transaction(function () use ($prepared, $zoneId, $code) {
            $existing = Alert::where('zone_id', $zoneId)
                ->where('code', $code)
                ->where(function ($query) {
                    $query->where('status', 'ACTIVE')->orWhere('status', 'active');
                })
                ->lockForUpdate()
                ->first();

            if (! $existing && $this->shouldRateLimit($code, $zoneId)) {
                Log::warning('Alert creation rate limited', [
                    'code' => $code,
                    'zone_id' => $zoneId,
                ]);

                return [
                    'alert' => null,
                    'created' => false,
                    'event_id' => null,
                    'rate_limited' => true,
                ];
            }

            $now = now();
            $nowIso = $now->toIso8601String();

            if ($existing) {
                DB::table('alerts')
                    ->where('id', $existing->id)
                    ->increment('error_count');

                $existing->refresh();
                $currentCount = (int) ($existing->error_count ?? 1);

                $existingDetails = $this->normalizeDetails($existing->details);
                $mergedDetails = $this->mergeAlertDetails($existingDetails, $prepared['details']);
                $mergedDetails['count'] = $currentCount;
                $mergedDetails['last_seen_at'] = $nowIso;
                $mergedDetails['alert_id'] = $existing->id;

                $existing->update([
                    'source' => $prepared['source'],
                    'type' => $prepared['type'],
                    'details' => $mergedDetails,
                    'category' => $prepared['category'],
                    'severity' => $prepared['severity'],
                    'node_uid' => $prepared['node_uid'] ?? $existing->node_uid,
                    'hardware_id' => $prepared['hardware_id'] ?? $existing->hardware_id,
                    'last_seen_at' => $now,
                    'first_seen_at' => $existing->first_seen_at ?? $existing->created_at ?? $now,
                ]);

                $fresh = $existing->fresh();

                Log::info('Alert updated', [
                    'alert_id' => $existing->id,
                    'code' => $code,
                    'error_count' => $currentCount,
                    'zone_id' => $zoneId,
                    'severity' => $prepared['severity'],
                ]);

                $eventId = null;
                if ($zoneId) {
                    $eventId = DB::table('zone_events')->insertGetId([
                        'zone_id' => $zoneId,
                        'type' => 'ALERT_UPDATED',
                        'payload_json' => json_encode($this->buildEventPayload($fresh, 'updated', [
                            'updated_at' => $nowIso,
                            'error_count' => $currentCount,
                        ])),
                        'created_at' => $now,
                    ]);
                }

                DB::afterCommit(function () use ($fresh) {
                    $this->broadcastAlertUpdated($fresh);
                });

                return [
                    'alert' => $fresh,
                    'created' => false,
                    'event_id' => $eventId,
                ];
            }

            $newDetails = $this->mergeAlertDetails([], $prepared['details']);
            $newDetails['count'] = 1;
            $newDetails['first_seen_at'] = $nowIso;
            $newDetails['last_seen_at'] = $nowIso;

            $alert = Alert::create([
                'zone_id' => $zoneId,
                'source' => $prepared['source'],
                'code' => $code,
                'type' => $prepared['type'],
                'status' => 'ACTIVE',
                'error_count' => 1,
                'details' => $newDetails,
                'category' => $prepared['category'],
                'severity' => $prepared['severity'],
                'node_uid' => $prepared['node_uid'],
                'hardware_id' => $prepared['hardware_id'],
                'first_seen_at' => $now,
                'last_seen_at' => $now,
                'created_at' => $now,
            ]);

            Log::info('Alert created', [
                'alert_id' => $alert->id,
                'code' => $code,
                'zone_id' => $zoneId,
                'severity' => $prepared['severity'],
            ]);

            $eventId = null;
            if ($zoneId) {
                $eventId = DB::table('zone_events')->insertGetId([
                    'zone_id' => $zoneId,
                    'type' => 'ALERT_CREATED',
                    'payload_json' => json_encode($this->buildEventPayload($alert, 'created', [
                        'created_at' => $nowIso,
                    ])),
                    'created_at' => $now,
                ]);
            }

            DB::afterCommit(function () use ($alert) {
                $this->broadcastAlertCreated($alert);
            });

            return [
                'alert' => $alert,
                'created' => true,
                'event_id' => $eventId,
            ];
        });
    }

    /**
     * Закрыть активный алерт по ключу (zone_id, code).
     *
     * @param int|null $zoneId ID зоны (null для unassigned alert)
     * @param string $code Код алерта
     * @param array<string, mixed> $context Дополнительный контекст
     * @return array{resolved: bool, alert: Alert|null, event_id: int|null}
     */
    public function resolveByCode(?int $zoneId, string $code, array $context = []): array
    {
        $normalizedCode = $this->alertCatalog->normalizeCode($code);

        return DB::transaction(function () use ($zoneId, $normalizedCode, $context) {
            $query = Alert::query()
                ->where('code', $normalizedCode)
                ->where(function ($statusQuery) {
                    $statusQuery->where('status', 'ACTIVE')->orWhere('status', 'active');
                });

            if ($zoneId === null) {
                $query->whereNull('zone_id');
            } else {
                $query->where('zone_id', $zoneId);
            }

            $alert = $query->lockForUpdate()->first();
            if (! $alert) {
                return [
                    'resolved' => false,
                    'alert' => null,
                    'event_id' => null,
                ];
            }

            $now = now();
            $nowIso = $now->toIso8601String();
            $details = $this->normalizeDetails($alert->details);

            if (isset($context['details']) && is_array($context['details'])) {
                $details = $this->mergeAlertDetails($details, $context['details']);
            }

            $details['resolved_at'] = $nowIso;
            $details['status'] = 'RESOLVED';

            $alert->update([
                'status' => 'RESOLVED',
                'resolved_at' => $now,
                'details' => $details,
                'last_seen_at' => $now,
            ]);

            $fresh = $alert->fresh();

            $eventId = null;
            if ($fresh->zone_id) {
                $eventId = DB::table('zone_events')->insertGetId([
                    'zone_id' => $fresh->zone_id,
                    'type' => 'ALERT_RESOLVED',
                    'payload_json' => json_encode($this->buildEventPayload($fresh, 'resolved', [
                        'resolved_at' => $nowIso,
                    ])),
                    'created_at' => $now,
                ]);
            }

            DB::afterCommit(function () use ($fresh) {
                $this->broadcastAlertUpdated($fresh);
            });

            Log::info('Alert resolved by code', [
                'alert_id' => $fresh->id,
                'zone_id' => $zoneId,
                'code' => $normalizedCode,
            ]);

            return [
                'resolved' => true,
                'alert' => $fresh,
                'event_id' => $eventId,
            ];
        });
    }

    /**
     * Подтвердить/принять алерт.
     */
    public function acknowledge(Alert $alert): Alert
    {
        return DB::transaction(function () use ($alert) {
            if ($this->normalizeStatus((string) $alert->status) === 'RESOLVED') {
                throw new \DomainException('Alert is already resolved');
            }

            $now = now();
            $details = $this->normalizeDetails($alert->details);
            $details['resolved_at'] = $now->toIso8601String();

            $alert->update([
                'status' => 'RESOLVED',
                'resolved_at' => $now,
                'last_seen_at' => $now,
                'details' => $details,
            ]);

            $fresh = $alert->fresh();

            if ($fresh->zone_id) {
                DB::table('zone_events')->insert([
                    'zone_id' => $fresh->zone_id,
                    'type' => 'ALERT_RESOLVED',
                    'payload_json' => json_encode($this->buildEventPayload($fresh, 'resolved', [
                        'resolved_at' => $now->toIso8601String(),
                    ])),
                    'created_at' => $now,
                ]);
            }

            Log::info('Alert acknowledged', ['alert_id' => $fresh->id]);
            return $fresh;
        });
    }

    /**
     * Сохранить алерт в pending_alerts для последующей обработки.
     *
     * @param array<string, mixed> $alertData
     */
    private function saveToPendingAlerts(array $alertData, \Exception $e): void
    {
        try {
            DB::table('pending_alerts')->insert([
                'zone_id' => $alertData['zone_id'] ?? null,
                'source' => $alertData['source'] ?? 'biz',
                'code' => $alertData['code'] ?? null,
                'type' => $alertData['type'] ?? 'unknown',
                'details' => isset($alertData['details']) ? json_encode($alertData['details']) : null,
                'status' => 'pending',
                'attempts' => 0,
                'max_attempts' => 3,
                'last_error' => $e->getMessage(),
                'next_retry_at' => now(),
                'moved_to_dlq_at' => null,
                'created_at' => now(),
                'updated_at' => now(),
            ]);

            Log::warning('Alert saved to pending_alerts due to creation error', [
                'error' => $e->getMessage(),
                'alert_data' => $alertData,
            ]);
        } catch (\Exception $saveException) {
            Log::error('Failed to save alert to pending_alerts', [
                'original_error' => $e->getMessage(),
                'save_error' => $saveException->getMessage(),
                'alert_data' => $alertData,
            ]);
        }
    }

    private function shouldRateLimit(string $errorCode, ?int $zoneId): bool
    {
        if (! config('alerts.rate_limiting.enabled', true)) {
            return false;
        }

        $criticalCodes = config('alerts.rate_limiting.critical_codes', []);
        if (in_array($errorCode, $criticalCodes, true)) {
            return false;
        }

        $maxPerMinute = (int) config('alerts.rate_limiting.max_per_minute', 10);
        $count = Alert::where('zone_id', $zoneId)
            ->where('created_at', '>', now()->subMinute())
            ->count();

        if ($count >= $maxPerMinute) {
            Log::warning('Alert rate limit exceeded', [
                'code' => $errorCode,
                'zone_id' => $zoneId,
                'count' => $count,
                'max_per_minute' => $maxPerMinute,
            ]);
            return true;
        }

        return false;
    }

    /**
     * @param array<string, mixed> $data
     * @return array<string, mixed>
     */
    private function prepareAlertPayload(array $data): array
    {
        $zoneId = isset($data['zone_id']) && is_numeric($data['zone_id']) ? (int) $data['zone_id'] : null;
        $details = $this->normalizeDetails($data['details'] ?? []);

        $rawCode = is_string($data['code'] ?? null) ? $data['code'] : ($details['code'] ?? null);
        $normalizedCode = $this->alertCatalog->normalizeCode($rawCode);
        if ($normalizedCode === '') {
            $normalizedCode = 'unknown_alert';
        }

        $catalogResolved = $this->alertCatalog->resolve(
            $normalizedCode,
            $data['source'] ?? ($details['source'] ?? null),
            $details,
        );

        $source = $this->normalizeSource($data['source'] ?? null)
            ?? $this->normalizeSource($details['source'] ?? null)
            ?? $catalogResolved['source'];

        $severity = $this->normalizeSeverity($data['severity'] ?? null)
            ?? $this->normalizeSeverity($details['severity'] ?? null)
            ?? $this->normalizeSeverity($details['level'] ?? null)
            ?? $catalogResolved['severity'];

        $category = $this->normalizeCategory($data['category'] ?? null)
            ?? $this->normalizeCategory($details['category'] ?? null)
            ?? $catalogResolved['category'];

        $nodeUid = $this->normalizeString($data['node_uid'] ?? null)
            ?? $this->normalizeString($details['node_uid'] ?? null);

        $hardwareId = $this->normalizeString($data['hardware_id'] ?? null)
            ?? $this->normalizeString($details['hardware_id'] ?? null);

        $type = $this->normalizeString($data['type'] ?? null)
            ?? $this->normalizeString($details['type'] ?? null)
            ?? $this->normalizeString($catalogResolved['title'] ?? null)
            ?? 'unknown';

        $status = $this->normalizeStatus($data['status'] ?? 'ACTIVE');

        $enrichedDetails = $details;
        $enrichedDetails['code'] = $normalizedCode;
        $enrichedDetails['source'] = $source;
        $enrichedDetails['severity'] = $severity;
        $enrichedDetails['category'] = $category;
        $enrichedDetails['title'] = $catalogResolved['title'];
        $enrichedDetails['description'] = $catalogResolved['description'];
        $enrichedDetails['recommendation'] = $catalogResolved['recommendation'];

        if (! isset($enrichedDetails['message']) || ! is_string($enrichedDetails['message']) || trim($enrichedDetails['message']) === '') {
            $enrichedDetails['message'] = $catalogResolved['description'];
        }

        if ($nodeUid !== null) {
            $enrichedDetails['node_uid'] = $nodeUid;
        }
        if ($hardwareId !== null) {
            $enrichedDetails['hardware_id'] = $hardwareId;
        }

        $tsDevice = $this->normalizeString($data['ts_device'] ?? null)
            ?? $this->normalizeString($enrichedDetails['ts_device'] ?? null);
        if ($tsDevice !== null) {
            $enrichedDetails['ts_device'] = $tsDevice;
        }

        return [
            'zone_id' => $zoneId,
            'source' => $source,
            'code' => $normalizedCode,
            'type' => $type,
            'status' => $status,
            'details' => $enrichedDetails,
            'severity' => $severity,
            'category' => $category,
            'node_uid' => $nodeUid,
            'hardware_id' => $hardwareId,
        ];
    }

    /**
     * @param array<string, mixed> $base
     * @param array<string, mixed> $extra
     * @return array<string, mixed>
     */
    private function mergeAlertDetails(array $base, array $extra): array
    {
        $merged = array_merge($base, $extra);

        if (isset($base['first_seen_at']) && ! isset($merged['first_seen_at'])) {
            $merged['first_seen_at'] = $base['first_seen_at'];
        }

        return $merged;
    }

    /**
     * @param mixed $details
     * @return array<string, mixed>
     */
    private function normalizeDetails(mixed $details): array
    {
        if (is_array($details)) {
            return $details;
        }

        if (is_string($details) && $details !== '') {
            $decoded = json_decode($details, true);
            if (is_array($decoded)) {
                return $decoded;
            }
        }

        return [];
    }

    private function normalizeSource(mixed $value): ?string
    {
        if (! is_string($value)) {
            return null;
        }

        $normalized = strtolower(trim($value));

        return in_array($normalized, ['biz', 'infra', 'node'], true) ? $normalized : null;
    }

    private function normalizeSeverity(mixed $value): ?string
    {
        if (! is_string($value)) {
            return null;
        }

        $normalized = strtolower(trim($value));

        return in_array($normalized, ['info', 'warning', 'error', 'critical'], true)
            ? $normalized
            : null;
    }

    private function normalizeCategory(mixed $value): ?string
    {
        if (! is_string($value)) {
            return null;
        }

        $normalized = strtolower(trim($value));

        return in_array(
            $normalized,
            ['agronomy', 'infrastructure', 'operations', 'node', 'config', 'safety', 'other'],
            true
        ) ? $normalized : null;
    }

    private function normalizeStatus(mixed $value): string
    {
        $normalized = strtoupper(trim((string) $value));

        return $normalized === 'RESOLVED' ? 'RESOLVED' : 'ACTIVE';
    }

    private function normalizeString(mixed $value): ?string
    {
        if (! is_string($value)) {
            return null;
        }

        $normalized = trim($value);

        return $normalized === '' ? null : $normalized;
    }

    /**
     * @param array<string, mixed> $extra
     * @return array<string, mixed>
     */
    private function buildEventPayload(Alert $alert, string $action, array $extra = []): array
    {
        $details = $this->normalizeDetails($alert->details);

        return array_merge([
            'alert_id' => $alert->id,
            'action' => $action,
            'code' => $alert->code,
            'type' => $alert->type,
            'source' => $alert->source,
            'status' => $alert->status,
            'severity' => $alert->severity,
            'category' => $alert->category,
            'zone_id' => $alert->zone_id,
            'node_uid' => $alert->node_uid,
            'hardware_id' => $alert->hardware_id,
            'error_count' => $alert->error_count,
            'message' => $details['message'] ?? $details['description'] ?? null,
            'recommendation' => $details['recommendation'] ?? null,
            'details' => $details,
        ], $extra);
    }

    /**
     * Отправить AlertCreated event через WebSocket.
     */
    private function broadcastAlertCreated(Alert $alert): void
    {
        event(new \App\Events\AlertCreated($this->buildRealtimePayload($alert)));
    }

    /**
     * Отправить AlertUpdated event через WebSocket.
     */
    private function broadcastAlertUpdated(Alert $alert): void
    {
        event(new \App\Events\AlertUpdated($this->buildRealtimePayload($alert)));
    }

    /**
     * @return array<string, mixed>
     */
    private function buildRealtimePayload(Alert $alert): array
    {
        $details = $this->normalizeDetails($alert->details);

        return [
            'id' => $alert->id,
            'type' => $alert->type,
            'source' => $alert->source,
            'code' => $alert->code,
            'status' => $alert->status,
            'zone_id' => $alert->zone_id,
            'details' => $details,
            'category' => $alert->category,
            'severity' => $alert->severity,
            'node_uid' => $alert->node_uid,
            'hardware_id' => $alert->hardware_id,
            'error_count' => $alert->error_count,
            'first_seen_at' => $alert->first_seen_at?->toIso8601String(),
            'last_seen_at' => $alert->last_seen_at?->toIso8601String(),
            'resolved_at' => $alert->resolved_at?->toIso8601String(),
            'created_at' => $alert->created_at?->toIso8601String(),
        ];
    }
}
