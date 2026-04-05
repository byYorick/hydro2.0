<?php

namespace App\Services;

use App\Events\ZoneUpdated;
use App\Exceptions\ZoneRuntimeSwitchDeniedException;
use App\Models\Command;
use App\Models\NodeChannel;
use App\Models\Zone;
use App\Models\ZoneEvent;
use App\Support\ZoneNodeChannelScope;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Schema;
use Illuminate\Support\Str;

class ZoneService
{
    /**
     * Создать зону
     */
    public function create(array $data): Zone
    {
        return DB::transaction(function () use ($data) {
            // Генерируем UID, если не указан
            if (empty($data['uid'])) {
                $data['uid'] = $this->generateZoneUid($data['name'] ?? 'untitled');
            }

            $data['status'] = 'NEW';

            $zone = Zone::create($data);
            $this->ensureCorrectionConfigBootstrap((int) $zone->id);
            $this->ensureLogicProfileBootstrap($zone->fresh());
            Log::info('Zone created', ['zone_id' => $zone->id, 'uid' => $zone->uid, 'name' => $zone->name]);

            // Dispatch event для уведомления Python-сервиса
            event(new ZoneUpdated($zone));

            return $zone;
        });
    }

    /**
     * Генерирует UID для зоны на основе названия
     *
     * @param  string  $name  Название зоны (может быть на русском)
     * @return string Сгенерированный UID в формате zn-{transliterated-name}
     */
    private function generateZoneUid(string $name): string
    {
        $prefix = 'zn-';

        if (empty($name) || trim($name) === '') {
            return $prefix.'untitled-'.strtolower(Str::random(6));
        }

        // Используем Str::slug для транслитерации и нормализации
        // Str::slug автоматически транслитерирует русские буквы
        $transliterated = Str::slug(trim($name), '-');

        // Если после обработки ничего не осталось, используем значение по умолчанию
        if (empty($transliterated)) {
            $transliterated = 'untitled-'.strtolower(Str::random(6));
        }

        // Ограничиваем длину (оставляем место для префикса и суффикса)
        $maxLength = 50 - strlen($prefix);
        if (strlen($transliterated) > $maxLength) {
            $transliterated = substr($transliterated, 0, $maxLength);
            // Убираем возможный дефис в конце после обрезки
            $transliterated = rtrim($transliterated, '-');
        }

        $uid = $prefix.$transliterated;

        // Проверяем уникальность UID и добавляем суффикс, если нужно
        $counter = 0;
        $originalUid = $uid;
        while (Zone::where('uid', $uid)->exists()) {
            $counter++;
            $suffix = '-'.$counter;
            $maxLengthWithSuffix = $maxLength - strlen($suffix);
            $base = substr($transliterated, 0, $maxLengthWithSuffix);
            $uid = $prefix.rtrim($base, '-').$suffix;

            // Защита от бесконечного цикла
            if ($counter > 1000) {
                $uid = $originalUid.'-'.time();
                break;
            }
        }

        return $uid;
    }

    /**
     * Обновить зону
     */
    public function update(Zone $zone, array $data): Zone
    {
        return DB::transaction(function () use ($zone, $data) {
            if (
                array_key_exists('automation_runtime', $data)
                && (string) $data['automation_runtime'] !== (string) $zone->automation_runtime
                && DB::getDriverName() === 'pgsql'
            ) {
                DB::statement('SELECT pg_advisory_xact_lock(?)', [(int) $zone->id]);
                $zone->refresh();
            }

            $this->assertAutomationRuntimeSwitchAllowed($zone, $data);
            $zone->update($data);
            Log::info('Zone updated', ['zone_id' => $zone->id]);
            $zone = $zone->fresh();
            if ((string) ($zone->automation_runtime ?? '') === 'ae3') {
                $this->ensureAe3AutomationBootstrap($zone);
            }

            // Dispatch event для уведомления Python-сервиса
            event(new ZoneUpdated($zone));

            return $zone;
        });
    }

    /**
     * Материализует документы authority для зоны и активирует дефолтный zone.logic_profile (WORKING),
     * если для runtime AE3 их ещё нет. Нужно перед проверкой готовности и запуском цикла.
     */
    public function ensureAe3AutomationBootstrap(Zone $zone): void
    {
        if (strtolower(trim((string) ($zone->automation_runtime ?? ''))) !== 'ae3') {
            return;
        }
        $zoneId = (int) $zone->id;
        if ($zoneId <= 0) {
            return;
        }
        $this->ensureCorrectionConfigBootstrap($zoneId);
        $this->ensureLogicProfileBootstrap($zone->fresh());
    }

    private function ensureCorrectionConfigBootstrap(int $zoneId): void
    {
        if ($zoneId <= 0) {
            return;
        }
        app(AutomationConfigDocumentService::class)->ensureZoneDefaults($zoneId);
    }

    private function ensureLogicProfileBootstrap(Zone $zone): void
    {
        $zoneId = (int) $zone->id;
        if ($zoneId <= 0) {
            return;
        }

        $profiles = app(ZoneLogicProfileService::class);
        if ($profiles->resolveActiveProfileForZone($zoneId) !== null) {
            return;
        }

        $profiles->upsertProfile(
            zone: $zone,
            mode: ZoneLogicProfileCatalog::MODE_WORKING,
            subsystems: $this->defaultAutomationSubsystems(),
            activate: true,
            userId: null,
        );
    }

    /**
     * @return array<string, mixed>
     */
    private function defaultAutomationSubsystems(): array
    {
        return [
            'diagnostics' => [
                'enabled' => true,
                'execution' => [
                    'workflow' => 'cycle_start',
                    'topology' => 'two_tank_drip_substrate_trays',
                ],
            ],
        ];
    }

    private function assertAutomationRuntimeSwitchAllowed(Zone $zone, array $data): void
    {
        if (! array_key_exists('automation_runtime', $data)) {
            return;
        }

        $targetRuntime = (string) $data['automation_runtime'];
        if ($targetRuntime === (string) $zone->automation_runtime) {
            return;
        }

        if (! Schema::hasTable('ae_tasks') || ! Schema::hasTable('ae_zone_leases') || ! Schema::hasTable('ae_commands')) {
            return;
        }

        $activeTask = DB::table('ae_tasks')
            ->select('id', 'status', 'claimed_by', 'updated_at')
            ->where('zone_id', $zone->id)
            ->whereIn('status', ['pending', 'claimed', 'running', 'waiting_command'])
            ->orderByDesc('updated_at')
            ->orderByDesc('id')
            ->first();

        if ($activeTask) {
            throw new ZoneRuntimeSwitchDeniedException([
                'zone_id' => $zone->id,
                'from_runtime' => (string) $zone->automation_runtime,
                'to_runtime' => $targetRuntime,
                'blocker' => 'active_task',
                'task_id' => (int) $activeTask->id,
                'task_status' => (string) $activeTask->status,
                'claimed_by' => $activeTask->claimed_by ? (string) $activeTask->claimed_by : null,
            ]);
        }

        $activeLease = DB::table('ae_zone_leases')
            ->select('owner', 'leased_until')
            ->where('zone_id', $zone->id)
            ->where('leased_until', '>', now())
            ->orderByDesc('leased_until')
            ->first();

        if ($activeLease) {
            throw new ZoneRuntimeSwitchDeniedException([
                'zone_id' => $zone->id,
                'from_runtime' => (string) $zone->automation_runtime,
                'to_runtime' => $targetRuntime,
                'blocker' => 'active_lease',
                'owner' => (string) $activeLease->owner,
                'leased_until' => $activeLease->leased_until,
            ]);
        }

        $indeterminateCommand = DB::table('ae_commands as commands')
            ->join('ae_tasks as tasks', 'tasks.id', '=', 'commands.task_id')
            ->select(
                'commands.id as ae_command_id',
                'commands.publish_status',
                'commands.external_id',
                'tasks.id as task_id',
                'tasks.status as task_status'
            )
            ->where('tasks.zone_id', $zone->id)
            ->whereIn('commands.publish_status', ['pending', 'accepted'])
            ->whereNull('commands.terminal_status')
            ->orderByDesc('commands.updated_at')
            ->orderByDesc('commands.id')
            ->first();

        if ($indeterminateCommand) {
            throw new ZoneRuntimeSwitchDeniedException([
                'zone_id' => $zone->id,
                'from_runtime' => (string) $zone->automation_runtime,
                'to_runtime' => $targetRuntime,
                'blocker' => 'indeterminate_command_state',
                'task_id' => (int) $indeterminateCommand->task_id,
                'task_status' => (string) $indeterminateCommand->task_status,
                'ae_command_id' => (int) $indeterminateCommand->ae_command_id,
                'publish_status' => (string) $indeterminateCommand->publish_status,
                'external_id' => $indeterminateCommand->external_id ? (string) $indeterminateCommand->external_id : null,
            ]);
        }
    }

    /**
     * Удалить зону (с проверкой инвариантов)
     */
    public function delete(Zone $zone): void
    {
        DB::transaction(function () use ($zone) {
            // Проверка: нельзя удалить зону с активным циклом
            if ($zone->activeGrowCycle) {
                throw new \DomainException('Cannot delete zone with active grow cycle. Please finish or abort cycle first.');
            }

            // Проверка: нельзя удалить зону с привязанными узлами
            if ($zone->nodes()->count() > 0) {
                throw new \DomainException('Cannot delete zone with attached nodes. Please detach nodes first.');
            }

            $zoneId = $zone->id;
            $zoneName = $zone->name;
            $zone->delete();
            Log::info('Zone deleted', ['zone_id' => $zoneId, 'name' => $zoneName]);
        });
    }

    /**
     * Пауза/возобновление зоны
     */
    public function pause(Zone $zone): Zone
    {
        if ($zone->status === 'PAUSED') {
            throw new \DomainException('Zone is already paused');
        }

        return DB::transaction(function () use ($zone) {
            try {
                $oldStatus = $zone->status;
                $zone->update(['status' => 'PAUSED']);

                // Создаем zone_event
                $hasPayloadJson = Schema::hasColumn('zone_events', 'payload_json');

                $eventPayload = json_encode([
                    'zone_id' => $zone->id,
                    'from_status' => $oldStatus ?? null,
                    'to_status' => 'PAUSED',
                    'paused_at' => now()->toIso8601String(),
                ]);

                $eventData = [
                    'zone_id' => $zone->id,
                    'type' => 'CYCLE_PAUSED',
                    'created_at' => now(),
                ];

                if ($hasPayloadJson) {
                    $eventData['payload_json'] = $eventPayload;
                } else {
                    $eventData['details'] = $eventPayload;
                }

                DB::table('zone_events')->insert($eventData);

                Log::info('Zone paused', ['zone_id' => $zone->id]);
                $zone = $zone->fresh();

                // Dispatch event для уведомления Python-сервиса
                try {
                    event(new ZoneUpdated($zone));
                } catch (\Exception $e) {
                    // Игнорируем ошибки при dispatch event, это не критично
                    Log::warning('Failed to dispatch ZoneUpdated event', [
                        'zone_id' => $zone->id,
                        'error' => $e->getMessage(),
                    ]);
                }

                return $zone;
            } catch (\Exception $e) {
                Log::error('Error in ZoneService::pause', [
                    'zone_id' => $zone->id,
                    'error' => $e->getMessage(),
                    'trace' => $e->getTraceAsString(),
                ]);
                throw $e;
            }
        });
    }

    /**
     * Возобновление зоны
     */
    public function resume(Zone $zone): Zone
    {
        if ($zone->status !== 'PAUSED') {
            throw new \DomainException('Zone is not paused');
        }

        return DB::transaction(function () use ($zone) {
            $zone->update(['status' => 'RUNNING']);

            // Создаем zone_event
            $hasPayloadJson = Schema::hasColumn('zone_events', 'payload_json');

            $eventPayload = json_encode([
                'zone_id' => $zone->id,
                'from_status' => 'PAUSED',
                'to_status' => 'RUNNING',
                'resumed_at' => now()->toIso8601String(),
            ]);

            $eventData = [
                'zone_id' => $zone->id,
                'type' => 'CYCLE_RESUMED',
                'created_at' => now(),
            ];

            if ($hasPayloadJson) {
                $eventData['payload_json'] = $eventPayload;
            } else {
                $eventData['details'] = $eventPayload;
            }

            DB::table('zone_events')->insert($eventData);

            Log::info('Zone resumed', ['zone_id' => $zone->id]);
            $zone = $zone->fresh();

            // Dispatch event для уведомления Python-сервиса
            event(new ZoneUpdated($zone));

            return $zone;
        });
    }

    /**
     * Калибровка дозирующей помпы (ml/sec).
     */
    public function calibratePump(Zone $zone, array $data): array
    {
        $channelBelongsToZone = ZoneNodeChannelScope::belongsToZone(
            $zone->id,
            (int) ($data['node_channel_id'] ?? 0)
        );
        if (! $channelBelongsToZone) {
            $invalidChannelId = (int) ($data['node_channel_id'] ?? 0);
            throw new \DomainException(
                "node_channel_id={$invalidChannelId} does not belong to zone {$zone->id}"
            );
        }

        /** @var NodeChannel|null $channel */
        $channel = NodeChannel::query()
            ->with('node')
            ->find((int) $data['node_channel_id']);

        if (! $channel || ! $channel->node) {
            throw new \DomainException("node_channel_id={$data['node_channel_id']} not found");
        }

        $settings = app(AutomationConfigDocumentService::class)->getSystemPayloadByLegacyNamespace('pump_calibration', true);
        $durationSec = (int) $data['duration_sec'];
        $skipRun = (bool) ($data['skip_run'] ?? false);
        $manualOverride = (bool) ($data['manual_override'] ?? false);
        $runToken = ! empty($data['run_token']) ? (string) $data['run_token'] : (string) Str::uuid();
        $normalizedComponent = $this->normalizePumpCalibrationComponent($data['component'] ?? null);
        $actualMl = array_key_exists('actual_ml', $data) && $data['actual_ml'] !== null
            ? (float) $data['actual_ml']
            : null;

        $commandId = null;
        $startedAt = now();

        if (! $skipRun) {
            if ((string) ($channel->node->status ?? '') !== 'online') {
                throw new \DomainException("Node {$channel->node->uid} is offline; cannot run calibration");
            }

            $commandId = app(PythonBridgeService::class)->sendZoneCommand($zone, [
                'type' => 'run_pump',
                'node_uid' => $channel->node->uid,
                'channel' => $channel->channel,
                'params' => [
                    'duration_ms' => $durationSec * 1000,
                ],
            ]);

            ZoneEvent::create([
                'zone_id' => $zone->id,
                'type' => 'PUMP_CALIBRATION_STARTED',
                'payload_json' => [
                    'node_channel_id' => $channel->id,
                    'node_uid' => $channel->node->uid,
                    'channel' => $channel->channel,
                    'duration_sec' => $durationSec,
                    'component' => $normalizedComponent,
                    'run_token' => $runToken,
                    'command_id' => $commandId,
                    'start_time' => $startedAt->toIso8601String(),
                ],
            ]);

            if ($actualMl === null) {
                return [
                    'success' => true,
                    'status' => 'awaiting_actual_ml',
                    'node_channel_id' => $channel->id,
                    'node_uid' => $channel->node->uid,
                    'channel' => $channel->channel,
                    'duration_sec' => $durationSec,
                    'component' => $normalizedComponent,
                    'run_token' => $runToken,
                    'started_at' => $startedAt->toIso8601String(),
                ];
            }
        } elseif ($actualMl === null) {
            ZoneEvent::create([
                'zone_id' => $zone->id,
                'type' => 'PUMP_CALIBRATION_RUN_SKIPPED',
                'payload_json' => [
                    'node_channel_id' => $channel->id,
                    'node_uid' => $channel->node->uid,
                    'channel' => $channel->channel,
                    'duration_sec' => $durationSec,
                    'component' => $normalizedComponent,
                    'run_token' => $runToken,
                ],
            ]);

            return [
                'success' => true,
                'status' => 'awaiting_actual_ml',
                'node_channel_id' => $channel->id,
                'node_uid' => $channel->node->uid,
                'channel' => $channel->channel,
                'duration_sec' => $durationSec,
                'component' => $normalizedComponent,
                'run_token' => $runToken,
                'started_at' => $startedAt->toIso8601String(),
            ];
        }

        if ($actualMl <= 0) {
            throw new \DomainException('actual_ml must be greater than 0');
        }

        if ($skipRun && ! $manualOverride) {
            if (empty($data['run_token'])) {
                throw new \DomainException('run_token is required when saving calibration after a physical run');
            }
            $matchingRun = $this->findMatchingPumpCalibrationRun($zone, $runToken, $channel->id, $durationSec, $normalizedComponent);
            if (! $matchingRun) {
                throw new \DomainException('run_token does not match an active pump calibration run');
            }
            if ($this->hasCompletedPumpCalibrationRun($zone, $runToken)) {
                throw new \DomainException('run_token has already been consumed by a completed calibration save');
            }
            $this->assertPumpCalibrationRunCompleted($zone, $matchingRun->command_id ?? null);
        }

        $mlPerSec = round($actualMl / (float) $durationSec, 6);
        if ($mlPerSec <= 0) {
            throw new \DomainException('Calculated ml_per_sec must be greater than 0');
        }

        $mlPerSecMin = (float) ($settings['ml_per_sec_min'] ?? 0.01);
        $mlPerSecMax = (float) ($settings['ml_per_sec_max'] ?? 20.0);
        if ($mlPerSec < $mlPerSecMin || $mlPerSec > $mlPerSecMax) {
            throw new \DomainException("Calculated ml_per_sec must be within [{$mlPerSecMin}, {$mlPerSecMax}]");
        }

        $testVolumeL = array_key_exists('test_volume_l', $data) && $data['test_volume_l'] !== null ? (float) $data['test_volume_l'] : null;
        $ecBeforeMs = array_key_exists('ec_before_ms', $data) && $data['ec_before_ms'] !== null ? (float) $data['ec_before_ms'] : null;
        $ecAfterMs = array_key_exists('ec_after_ms', $data) && $data['ec_after_ms'] !== null ? (float) $data['ec_after_ms'] : null;
        $temperatureC = array_key_exists('temperature_c', $data) && $data['temperature_c'] !== null ? (float) $data['temperature_c'] : null;

        $kMsPerMlL = null;
        $deltaEcMs = null;
        if ($testVolumeL !== null || $ecBeforeMs !== null || $ecAfterMs !== null) {
            if ($testVolumeL === null || $ecBeforeMs === null || $ecAfterMs === null) {
                throw new \DomainException('test_volume_l, ec_before_ms and ec_after_ms must be provided together');
            }
            if ($testVolumeL <= 0) {
                throw new \DomainException('test_volume_l must be greater than 0');
            }
            if ($ecAfterMs <= $ecBeforeMs) {
                throw new \DomainException('ec_after_ms must be greater than ec_before_ms');
            }

            $deltaEcMs = round($ecAfterMs - $ecBeforeMs, 6);
            $mlPerL = $actualMl / $testVolumeL;
            if ($mlPerL <= 0) {
                throw new \DomainException('Calculated ml_per_l must be greater than 0');
            }

            $kMsPerMlL = round($deltaEcMs / $mlPerL, 6);
            if ($kMsPerMlL <= 0) {
                throw new \DomainException('Calculated k_ms_per_ml_l must be greater than 0');
            }
        }

        $finishedAt = now();
        $qualityScore = $kMsPerMlL !== null
            ? (float) ($settings['quality_score_with_k'] ?? 0.8)
            : (float) ($settings['quality_score_basic'] ?? 0.5);

        $calibrationPayload = [
            'ml_per_sec' => $mlPerSec,
            'duration_sec' => $durationSec,
            'actual_ml' => $actualMl,
            'component' => $normalizedComponent,
            'k_ms_per_ml_l' => $kMsPerMlL,
            'test_volume_l' => $testVolumeL,
            'ec_before_ms' => $ecBeforeMs,
            'ec_after_ms' => $ecAfterMs,
            'delta_ec_ms' => $deltaEcMs,
            'temperature_c' => $temperatureC,
            'calibrated_at' => $finishedAt->toIso8601String(),
        ];

        DB::transaction(function () use (
            $channel,
            $zone,
            $normalizedComponent,
            $mlPerSec,
            $kMsPerMlL,
            $durationSec,
            $actualMl,
            $testVolumeL,
            $ecBeforeMs,
            $ecAfterMs,
            $deltaEcMs,
            $temperatureC,
            $qualityScore,
            $runToken,
            $manualOverride,
            $finishedAt,
            $calibrationPayload
        ): void {
            DB::table('pump_calibrations')
                ->where('node_channel_id', $channel->id)
                ->where('is_active', true)
                ->update([
                    'is_active' => false,
                    'valid_to' => $finishedAt,
                    'updated_at' => $finishedAt,
                ]);

            DB::table('pump_calibrations')->insert([
                'node_channel_id' => $channel->id,
                'component' => $normalizedComponent,
                'ml_per_sec' => $mlPerSec,
                'k_ms_per_ml_l' => $kMsPerMlL,
                'duration_sec' => $durationSec,
                'actual_ml' => $actualMl,
                'test_volume_l' => $testVolumeL,
                'ec_before_ms' => $ecBeforeMs,
                'ec_after_ms' => $ecAfterMs,
                'delta_ec_ms' => $deltaEcMs,
                'temperature_c' => $temperatureC,
                'source' => 'manual_calibration',
                'quality_score' => $qualityScore,
                'sample_count' => 1,
                'valid_from' => $finishedAt,
                'is_active' => true,
                'meta' => json_encode([
                    'origin' => 'laravel_zone_calibrate_pump',
                    'compat_write_legacy_node_channel_config' => true,
                    'component' => $normalizedComponent,
                ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
                'created_at' => $finishedAt,
                'updated_at' => $finishedAt,
            ]);

            $channel->config = $this->mergeNodeChannelConfig($channel->config, [
                'pump_calibration' => $calibrationPayload,
            ]);
            $channel->save();

            ZoneEvent::create([
                'zone_id' => $zone->id,
                'type' => 'PUMP_CALIBRATION_FINISHED',
                'payload_json' => [
                    'node_channel_id' => $channel->id,
                    'node_uid' => $channel->node->uid,
                    'channel' => $channel->channel,
                    'component' => $normalizedComponent,
                    'duration_sec' => $durationSec,
                    'actual_ml' => $actualMl,
                    'ml_per_sec' => $mlPerSec,
                    'k_ms_per_ml_l' => $kMsPerMlL,
                    'test_volume_l' => $testVolumeL,
                    'ec_before_ms' => $ecBeforeMs,
                    'ec_after_ms' => $ecAfterMs,
                    'delta_ec_ms' => $deltaEcMs,
                    'temperature_c' => $temperatureC,
                    'run_token' => $runToken,
                    'manual_override' => $manualOverride,
                    'finished_at' => $finishedAt->toIso8601String(),
                ],
            ]);
        });

        return [
            'success' => true,
            'status' => 'calibrated',
            'node_channel_id' => $channel->id,
            'node_uid' => $channel->node->uid,
            'channel' => $channel->channel,
            'component' => $normalizedComponent,
            'duration_sec' => $durationSec,
            'actual_ml' => $actualMl,
            'ml_per_sec' => $mlPerSec,
            'k_ms_per_ml_l' => $kMsPerMlL,
            'test_volume_l' => $testVolumeL,
            'ec_before_ms' => $ecBeforeMs,
            'ec_after_ms' => $ecAfterMs,
            'delta_ec_ms' => $deltaEcMs,
            'temperature_c' => $temperatureC,
            'run_token' => $runToken,
            'calibrated_at' => $finishedAt->toIso8601String(),
        ];
    }

    private function normalizePumpCalibrationComponent(mixed $value): ?string
    {
        if ($value === null) {
            return null;
        }

        $normalized = str_replace(['-', ' '], '_', strtolower(trim((string) $value)));
        $aliases = [
            'phup' => 'ph_up',
            'phdown' => 'ph_down',
            'ph_base' => 'ph_up',
            'ph_acid' => 'ph_down',
            'base' => 'ph_up',
            'acid' => 'ph_down',
        ];

        return $aliases[$normalized] ?? $normalized;
    }

    private function findMatchingPumpCalibrationRun(
        Zone $zone,
        string $runToken,
        int $nodeChannelId,
        int $durationSec,
        ?string $component
    ): ?object {
        return DB::table('zone_events')
            ->selectRaw("payload_json->>'command_id' as command_id")
            ->where('zone_id', $zone->id)
            ->where('type', 'PUMP_CALIBRATION_STARTED')
            ->whereRaw("payload_json->>'run_token' = ?", [$runToken])
            ->whereRaw("(payload_json->>'node_channel_id')::int = ?", [$nodeChannelId])
            ->whereRaw("payload_json->>'duration_sec' = ?", [(string) $durationSec])
            ->whereRaw("payload_json->>'component' IS NOT DISTINCT FROM ?", [$component])
            ->orderByDesc('id')
            ->first();
    }

    private function hasCompletedPumpCalibrationRun(Zone $zone, string $runToken): bool
    {
        return DB::table('zone_events')
            ->where('zone_id', $zone->id)
            ->where('type', 'PUMP_CALIBRATION_FINISHED')
            ->whereRaw("payload_json->>'run_token' = ?", [$runToken])
            ->exists();
    }

    private function assertPumpCalibrationRunCompleted(Zone $zone, ?string $commandId): void
    {
        if (! is_string($commandId) || trim($commandId) === '') {
            throw new \DomainException('run_token does not reference a published pump calibration command');
        }

        $command = Command::query()
            ->where('zone_id', $zone->id)
            ->where('cmd_id', $commandId)
            ->first();

        if (! $command) {
            throw new \DomainException('pump calibration run command is missing; cannot verify terminal status');
        }

        if (! $command->isFinal()) {
            throw new \DomainException(
                "pump calibration run is still {$command->status}; wait for terminal DONE before saving calibration"
            );
        }

        if ($command->status !== Command::STATUS_DONE) {
            throw new \DomainException(
                "pump calibration run ended with status {$command->status}; cannot save calibration"
            );
        }
    }

    private function mergeNodeChannelConfig(mixed $current, array $incoming): array
    {
        $currentConfig = is_array($current) ? $current : [];

        return $this->mergeAssocConfig($currentConfig, $incoming);
    }

    private function mergeAssocConfig(array $current, array $incoming): array
    {
        $merged = $current;

        foreach ($incoming as $key => $value) {
            $currentValue = $merged[$key] ?? null;
            if (
                is_string($key)
                && is_array($value)
                && ! array_is_list($value)
                && is_array($currentValue)
                && ! array_is_list($currentValue)
            ) {
                $merged[$key] = $this->mergeAssocConfig($currentValue, $value);

                continue;
            }

            $merged[$key] = $value;
        }

        return $merged;
    }

    /**
     * Завершить grow-cycle (harvest)
     */
    public function harvest(Zone $zone): Zone
    {
        return DB::transaction(function () use ($zone) {
            // Проверяем, что зона в статусе RUNNING или PAUSED
            if (! in_array($zone->status, ['RUNNING', 'PAUSED'])) {
                throw new \DomainException("Zone must be RUNNING or PAUSED to harvest. Current status: {$zone->status}");
            }

            // Обновляем статус зоны на HARVESTED
            $zone->update(['status' => 'HARVESTED']);

            // Закрываем активный цикл, если есть
            if ($zone->activeGrowCycle) {
                // Завершаем цикл через GrowCycleService
                // Это должно быть сделано через отдельный метод, но пока просто логируем
                Log::info('Active grow cycle found on harvest', [
                    'zone_id' => $zone->id,
                    'grow_cycle_id' => $zone->activeGrowCycle->id,
                ]);
            }

            // Создаем zone_event
            $hasPayloadJson = Schema::hasColumn('zone_events', 'payload_json');

            $eventPayload = json_encode([
                'zone_id' => $zone->id,
                'status' => 'HARVESTED',
                'harvested_at' => now()->toIso8601String(),
            ]);

            $eventData = [
                'zone_id' => $zone->id,
                'type' => 'CYCLE_HARVESTED',
                'created_at' => now(),
            ];

            if ($hasPayloadJson) {
                $eventData['payload_json'] = $eventPayload;
            } else {
                $eventData['details'] = $eventPayload;
            }

            DB::table('zone_events')->insert($eventData);

            Log::info('Zone cycle harvested', [
                'zone_id' => $zone->id,
            ]);

            $zone = $zone->fresh();

            // Dispatch event для уведомления Python-сервиса
            event(new ZoneUpdated($zone));

            return $zone;
        });
    }
}
