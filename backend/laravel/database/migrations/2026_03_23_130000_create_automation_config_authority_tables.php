<?php

use App\Services\AutomationConfigCompiler;
use App\Services\AutomationConfigDocumentService;
use App\Services\AutomationConfigRegistry;
use App\Services\AutomationRuntimeConfigService;
use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * @var array<int, int>
     */
    private array $legacyCorrectionPresetIdMap = [];

    public function up(): void
    {
        Schema::create('automation_config_documents', function (Blueprint $table): void {
            $table->id();
            $table->string('namespace', 128);
            $table->string('scope_type', 32);
            $table->unsignedBigInteger('scope_id');
            $table->unsignedInteger('schema_version')->default(1);
            $table->jsonb('payload')->default(DB::raw("'{}'::jsonb"));
            $table->string('status', 32)->default('valid');
            $table->string('source', 32)->default('migration');
            $table->string('checksum', 64);
            $table->foreignId('updated_by')->nullable()->constrained('users')->nullOnDelete();
            $table->timestamps();

            $table->unique(['namespace', 'scope_type', 'scope_id'], 'automation_config_documents_ns_scope_unique');
            $table->index(['scope_type', 'scope_id'], 'automation_config_documents_scope_idx');
        });

        Schema::create('automation_config_versions', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('document_id')->constrained('automation_config_documents')->cascadeOnDelete();
            $table->string('namespace', 128);
            $table->string('scope_type', 32);
            $table->unsignedBigInteger('scope_id');
            $table->unsignedInteger('schema_version')->default(1);
            $table->jsonb('payload')->default(DB::raw("'{}'::jsonb"));
            $table->string('status', 32)->default('valid');
            $table->string('source', 32)->default('migration');
            $table->string('checksum', 64);
            $table->foreignId('changed_by')->nullable()->constrained('users')->nullOnDelete();
            $table->timestampTz('changed_at');
            $table->timestamps();

            $table->index(['namespace', 'scope_type', 'scope_id'], 'automation_config_versions_scope_idx');
        });

        Schema::create('automation_effective_bundles', function (Blueprint $table): void {
            $table->id();
            $table->string('scope_type', 32);
            $table->unsignedBigInteger('scope_id');
            $table->string('bundle_revision', 64);
            $table->string('schema_revision', 64);
            $table->jsonb('config')->default(DB::raw("'{}'::jsonb"));
            $table->jsonb('violations')->default(DB::raw("'[]'::jsonb"));
            $table->string('status', 32)->default('valid');
            $table->timestampTz('compiled_at');
            $table->string('inputs_checksum', 64);
            $table->timestamps();

            $table->unique(['scope_type', 'scope_id'], 'automation_effective_bundles_scope_unique');
            $table->index(['bundle_revision'], 'automation_effective_bundles_revision_idx');
        });

        Schema::create('automation_config_violations', function (Blueprint $table): void {
            $table->id();
            $table->string('scope_type', 32);
            $table->unsignedBigInteger('scope_id');
            $table->string('namespace', 128);
            $table->string('path', 255)->default('');
            $table->string('code', 128);
            $table->string('severity', 32);
            $table->boolean('blocking')->default(false);
            $table->text('message');
            $table->timestampTz('detected_at');

            $table->index(['scope_type', 'scope_id'], 'automation_config_violations_scope_idx');
        });

        Schema::create('automation_config_presets', function (Blueprint $table): void {
            $table->id();
            $table->string('namespace', 128);
            $table->string('scope', 32)->default('custom');
            $table->boolean('is_locked')->default(false);
            $table->string('name');
            $table->string('slug')->unique();
            $table->text('description')->nullable();
            $table->unsignedInteger('schema_version')->default(1);
            $table->jsonb('payload')->default(DB::raw("'{}'::jsonb"));
            $table->foreignId('updated_by')->nullable()->constrained('users')->nullOnDelete();
            $table->timestamps();

            $table->index(['namespace', 'scope'], 'automation_config_presets_ns_scope_idx');
        });

        Schema::create('automation_config_preset_versions', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('preset_id')->constrained('automation_config_presets')->cascadeOnDelete();
            $table->string('namespace', 128);
            $table->string('scope', 32);
            $table->unsignedInteger('schema_version')->default(1);
            $table->jsonb('payload')->default(DB::raw("'{}'::jsonb"));
            $table->string('checksum', 64);
            $table->foreignId('changed_by')->nullable()->constrained('users')->nullOnDelete();
            $table->timestampTz('changed_at');
            $table->timestamps();
        });

        $this->backfillLegacyAuthority();
        $this->compileBackfilledAuthority();
    }

    public function down(): void
    {
        Schema::dropIfExists('automation_config_preset_versions');
        Schema::dropIfExists('automation_config_presets');
        Schema::dropIfExists('automation_config_violations');
        Schema::dropIfExists('automation_effective_bundles');
        Schema::dropIfExists('automation_config_versions');
        Schema::dropIfExists('automation_config_documents');
    }

    private function backfillLegacyAuthority(): void
    {
        $this->backfillSystemSettings();
        $this->backfillRuntimeOverrides();
        $this->backfillCorrectionPresets();
        $this->backfillZoneCorrectionConfigs();
        $this->backfillZonePidConfigs();
        $this->backfillZoneLogicProfiles();
        $this->backfillZoneProcessCalibrations();
        $this->backfillGrowCycleDocuments();
    }

    private function compileBackfilledAuthority(): void
    {
        /** @var AutomationConfigDocumentService $documents */
        $documents = app(AutomationConfigDocumentService::class);
        /** @var AutomationConfigCompiler $compiler */
        $compiler = app(AutomationConfigCompiler::class);

        $documents->ensureSystemDefaults();

        if (Schema::hasTable('zones')) {
            foreach (DB::table('zones')->pluck('id') as $zoneId) {
                $documents->ensureZoneDefaults((int) $zoneId);
            }
        }

        if (Schema::hasTable('grow_cycles')) {
            foreach (DB::table('grow_cycles')->pluck('id') as $cycleId) {
                $documents->ensureCycleDefaults((int) $cycleId);
            }
        }

        $compiler->compileSystemCascade();

        if (Schema::hasTable('grow_cycles')) {
            foreach (DB::table('grow_cycles')->pluck('id') as $cycleId) {
                $compiler->compileGrowCycleBundle((int) $cycleId);
            }
        }
    }

    private function backfillSystemSettings(): void
    {
        if (! Schema::hasTable('system_automation_settings')) {
            return;
        }

        $namespaceMap = [
            'automation_defaults' => AutomationConfigRegistry::NAMESPACE_SYSTEM_AUTOMATION_DEFAULTS,
            'automation_command_templates' => AutomationConfigRegistry::NAMESPACE_SYSTEM_COMMAND_TEMPLATES,
            'process_calibration_defaults' => AutomationConfigRegistry::NAMESPACE_SYSTEM_PROCESS_CALIBRATION_DEFAULTS,
            'pid_defaults_ph' => AutomationConfigRegistry::NAMESPACE_SYSTEM_PID_DEFAULTS_PH,
            'pid_defaults_ec' => AutomationConfigRegistry::NAMESPACE_SYSTEM_PID_DEFAULTS_EC,
            'pump_calibration' => AutomationConfigRegistry::NAMESPACE_SYSTEM_PUMP_CALIBRATION_POLICY,
            'sensor_calibration' => AutomationConfigRegistry::NAMESPACE_SYSTEM_SENSOR_CALIBRATION_POLICY,
        ];

        $rows = DB::table('system_automation_settings')->get();
        foreach ($rows as $row) {
            $authorityNamespace = $namespaceMap[$row->namespace] ?? null;
            if ($authorityNamespace === null) {
                continue;
            }

            $payload = is_array($row->config) ? $row->config : json_decode((string) $row->config, true);
            if (! is_array($payload)) {
                continue;
            }

            $this->upsertAuthorityDocument(
                namespace: $authorityNamespace,
                scopeType: AutomationConfigRegistry::SCOPE_SYSTEM,
                scopeId: 0,
                payload: $payload,
                updatedBy: $row->updated_by ?? null,
                updatedAt: $row->updated_at ?? now(),
                source: 'legacy_system_settings'
            );
        }
    }

    private function backfillRuntimeOverrides(): void
    {
        if (! Schema::hasTable('automation_runtime_overrides')) {
            return;
        }

        $payload = AutomationRuntimeConfigService::defaultSettingsMapStatic();
        $rows = DB::table('automation_runtime_overrides')->orderBy('id')->get();
        $updatedBy = null;
        $updatedAt = now();

        foreach ($rows as $row) {
            $payload[(string) $row->key] = $this->normalizeScalarValue($row->value);
            $updatedBy = $row->updated_by ?? $updatedBy;
            $updatedAt = $row->updated_at ?? $updatedAt;
        }

        if ($rows->isNotEmpty()) {
            $this->upsertAuthorityDocument(
                namespace: AutomationConfigRegistry::NAMESPACE_SYSTEM_RUNTIME,
                scopeType: AutomationConfigRegistry::SCOPE_SYSTEM,
                scopeId: 0,
                payload: $payload,
                updatedBy: $updatedBy,
                updatedAt: $updatedAt,
                source: 'legacy_runtime_overrides'
            );
        }
    }

    private function backfillCorrectionPresets(): void
    {
        if (! Schema::hasTable('zone_correction_presets')) {
            return;
        }

        $rows = DB::table('zone_correction_presets')->orderBy('id')->get();
        foreach ($rows as $row) {
            $payload = is_array($row->config) ? $row->config : json_decode((string) $row->config, true);
            if (! is_array($payload)) {
                $payload = [];
            }

            $presetId = $this->upsertAuthorityPreset(
                namespace: AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION,
                scope: (string) ($row->scope ?? 'custom'),
                isLocked: (bool) ($row->is_locked ?? false),
                name: (string) ($row->name ?? 'Preset'),
                slug: (string) ($row->slug ?? 'preset-'.$row->id),
                description: $row->description,
                payload: $payload,
                updatedBy: $row->updated_by ?? null,
                updatedAt: $row->updated_at ?? now()
            );

            $this->legacyCorrectionPresetIdMap[(int) $row->id] = $presetId;
        }
    }

    private function backfillZoneCorrectionConfigs(): void
    {
        if (! Schema::hasTable('zone_correction_configs')) {
            return;
        }

        $rows = DB::table('zone_correction_configs')->orderBy('id')->get();
        foreach ($rows as $row) {
            $payload = [
                'preset_id' => isset($row->preset_id) ? ($this->legacyCorrectionPresetIdMap[(int) $row->preset_id] ?? null) : null,
                'base_config' => $this->decodeJsonObject($row->base_config),
                'phase_overrides' => $this->decodeJsonObject($row->phase_overrides),
                'resolved_config' => $this->decodeJsonObject($row->resolved_config),
                'last_applied_at' => $row->last_applied_at,
                'last_applied_version' => $row->last_applied_version,
            ];

            $this->upsertAuthorityDocument(
                namespace: AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION,
                scopeType: AutomationConfigRegistry::SCOPE_ZONE,
                scopeId: (int) $row->zone_id,
                payload: $payload,
                updatedBy: $row->updated_by ?? null,
                updatedAt: $row->updated_at ?? now(),
                source: 'legacy_zone_correction'
            );
        }
    }

    private function backfillZonePidConfigs(): void
    {
        if (! Schema::hasTable('zone_pid_configs')) {
            return;
        }

        $rows = DB::table('zone_pid_configs')->orderBy('id')->get();
        foreach ($rows as $row) {
            $namespace = (string) $row->type === 'ec'
                ? AutomationConfigRegistry::NAMESPACE_ZONE_PID_EC
                : AutomationConfigRegistry::NAMESPACE_ZONE_PID_PH;

            $this->upsertAuthorityDocument(
                namespace: $namespace,
                scopeType: AutomationConfigRegistry::SCOPE_ZONE,
                scopeId: (int) $row->zone_id,
                payload: $this->decodeJsonObject($row->config),
                updatedBy: $row->updated_by ?? null,
                updatedAt: $row->updated_at ?? now(),
                source: 'legacy_zone_pid'
            );
        }
    }

    private function backfillZoneLogicProfiles(): void
    {
        if (! Schema::hasTable('zone_automation_logic_profiles')) {
            return;
        }

        $grouped = DB::table('zone_automation_logic_profiles')
            ->orderBy('zone_id')
            ->orderBy('id')
            ->get()
            ->groupBy('zone_id');

        foreach ($grouped as $zoneId => $rows) {
            $profiles = [];
            $activeMode = null;
            $updatedBy = null;
            $updatedAt = now();

            foreach ($rows as $row) {
                $mode = (string) $row->mode;
                $profiles[$mode] = [
                    'mode' => $mode,
                    'is_active' => (bool) ($row->is_active ?? false),
                    'subsystems' => $this->decodeJsonObject($row->subsystems),
                    'command_plans' => $this->decodeJsonObject($row->command_plans),
                    'created_by' => $row->created_by ?? null,
                    'updated_by' => $row->updated_by ?? null,
                    'created_at' => $row->created_at ? (string) $row->created_at : null,
                    'updated_at' => $row->updated_at ? (string) $row->updated_at : null,
                ];
                if ((bool) ($row->is_active ?? false)) {
                    $activeMode = $mode;
                }
                $updatedBy = $row->updated_by ?? $updatedBy;
                $updatedAt = $row->updated_at ?? $updatedAt;
            }

            $this->upsertAuthorityDocument(
                namespace: AutomationConfigRegistry::NAMESPACE_ZONE_LOGIC_PROFILE,
                scopeType: AutomationConfigRegistry::SCOPE_ZONE,
                scopeId: (int) $zoneId,
                payload: [
                    'active_mode' => $activeMode,
                    'profiles' => $profiles,
                ],
                updatedBy: $updatedBy,
                updatedAt: $updatedAt,
                source: 'legacy_zone_logic_profile'
            );
        }
    }

    private function backfillZoneProcessCalibrations(): void
    {
        if (! Schema::hasTable('zone_process_calibrations')) {
            return;
        }

        $rows = DB::table('zone_process_calibrations')
            ->where('is_active', true)
            ->orderBy('zone_id')
            ->orderByDesc('valid_from')
            ->orderByDesc('id')
            ->get();

        $seen = [];
        foreach ($rows as $row) {
            $mode = $this->normalizeProcessMode((string) $row->mode);
            $key = $row->zone_id.':'.$mode;
            if (isset($seen[$key])) {
                continue;
            }
            $seen[$key] = true;

            $this->upsertAuthorityDocument(
                namespace: $this->processModeToNamespace($mode),
                scopeType: AutomationConfigRegistry::SCOPE_ZONE,
                scopeId: (int) $row->zone_id,
                payload: [
                    'mode' => $mode,
                    'ec_gain_per_ml' => $row->ec_gain_per_ml,
                    'ph_up_gain_per_ml' => $row->ph_up_gain_per_ml,
                    'ph_down_gain_per_ml' => $row->ph_down_gain_per_ml,
                    'ph_per_ec_ml' => $row->ph_per_ec_ml,
                    'ec_per_ph_ml' => $row->ec_per_ph_ml,
                    'transport_delay_sec' => $row->transport_delay_sec,
                    'settle_sec' => $row->settle_sec,
                    'confidence' => $row->confidence,
                    'source' => $row->source,
                    'valid_from' => $row->valid_from ? (string) $row->valid_from : null,
                    'valid_to' => $row->valid_to ? (string) $row->valid_to : null,
                    'is_active' => (bool) ($row->is_active ?? true),
                    'meta' => $this->decodeJsonObject($row->meta),
                ],
                updatedBy: null,
                updatedAt: $row->updated_at ?? now(),
                source: 'legacy_zone_process_calibration'
            );
        }
    }

    private function backfillGrowCycleDocuments(): void
    {
        if (! Schema::hasTable('grow_cycles')) {
            return;
        }

        $cycles = DB::table('grow_cycles')
            ->leftJoin('grow_cycle_phases', 'grow_cycle_phases.id', '=', 'grow_cycles.current_phase_id')
            ->select([
                'grow_cycles.id',
                'grow_cycles.zone_id',
                'grow_cycles.recipe_revision_id',
                'grow_cycles.current_phase_id',
                'grow_cycle_phases.recipe_revision_phase_id as phase_id',
                'grow_cycle_phases.phase_index',
                'grow_cycle_phases.name',
                'grow_cycle_phases.ph_target',
                'grow_cycle_phases.ph_min',
                'grow_cycle_phases.ph_max',
                'grow_cycle_phases.ec_target',
                'grow_cycle_phases.ec_min',
                'grow_cycle_phases.ec_max',
                'grow_cycle_phases.irrigation_mode',
                'grow_cycle_phases.irrigation_interval_sec',
                'grow_cycle_phases.irrigation_duration_sec',
                'grow_cycle_phases.extensions',
                'grow_cycles.updated_at',
            ])
            ->get();

        foreach ($cycles as $cycle) {
            $startSnapshot = $cycle->current_phase_id ? [
                'cycle_id' => (int) $cycle->id,
                'zone_id' => (int) $cycle->zone_id,
                'recipe_revision_id' => (int) $cycle->recipe_revision_id,
                'phase' => [
                    'phase_id' => $cycle->phase_id,
                    'phase_index' => $cycle->phase_index,
                    'name' => $cycle->name,
                    'ph_target' => $cycle->ph_target,
                    'ph_min' => $cycle->ph_min,
                    'ph_max' => $cycle->ph_max,
                    'ec_target' => $cycle->ec_target,
                    'ec_min' => $cycle->ec_min,
                    'ec_max' => $cycle->ec_max,
                    'irrigation_mode' => $cycle->irrigation_mode,
                    'irrigation_interval_sec' => $cycle->irrigation_interval_sec,
                    'irrigation_duration_sec' => $cycle->irrigation_duration_sec,
                    'extensions' => $this->decodeJsonObject($cycle->extensions),
                ],
            ] : [];

            if ($startSnapshot !== []) {
                $this->upsertAuthorityDocument(
                    namespace: AutomationConfigRegistry::NAMESPACE_CYCLE_START_SNAPSHOT,
                    scopeType: AutomationConfigRegistry::SCOPE_GROW_CYCLE,
                    scopeId: (int) $cycle->id,
                    payload: $startSnapshot,
                    updatedBy: null,
                    updatedAt: $cycle->updated_at ?? now(),
                    source: 'legacy_grow_cycle_snapshot'
                );
            }

            if (! Schema::hasTable('grow_cycle_overrides')) {
                continue;
            }

            $manualOverrides = DB::table('grow_cycle_overrides')
                ->where('grow_cycle_id', $cycle->id)
                ->orderBy('id')
                ->get()
                ->map(fn ($row): array => [
                    'parameter' => $row->parameter,
                    'value_type' => $row->value_type,
                    'value' => $this->normalizeScalarValue($row->value),
                    'is_active' => (bool) ($row->is_active ?? true),
                    'applies_from' => $row->applies_from ? (string) $row->applies_from : null,
                    'applies_until' => $row->applies_until ? (string) $row->applies_until : null,
                ])
                ->values()
                ->all();

            if ($manualOverrides !== []) {
                $this->upsertAuthorityDocument(
                    namespace: AutomationConfigRegistry::NAMESPACE_CYCLE_MANUAL_OVERRIDES,
                    scopeType: AutomationConfigRegistry::SCOPE_GROW_CYCLE,
                    scopeId: (int) $cycle->id,
                    payload: $manualOverrides,
                    updatedBy: null,
                    updatedAt: $cycle->updated_at ?? now(),
                    source: 'legacy_grow_cycle_overrides'
                );
            }
        }
    }

    /**
     * @param  array<int|string, mixed>  $payload
     */
    private function upsertAuthorityDocument(
        string $namespace,
        string $scopeType,
        int $scopeId,
        array $payload,
        ?int $updatedBy,
        mixed $updatedAt,
        string $source,
    ): void {
        $timestamp = $updatedAt ?? now();
        $checksum = sha1(json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES));

        DB::table('automation_config_documents')->updateOrInsert(
            [
                'namespace' => $namespace,
                'scope_type' => $scopeType,
                'scope_id' => $scopeId,
            ],
            [
                'schema_version' => 1,
                'payload' => json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
                'status' => 'valid',
                'source' => $source,
                'checksum' => $checksum,
                'updated_by' => $updatedBy,
                'updated_at' => $timestamp,
                'created_at' => $timestamp,
            ]
        );

        $documentId = DB::table('automation_config_documents')
            ->where('namespace', $namespace)
            ->where('scope_type', $scopeType)
            ->where('scope_id', $scopeId)
            ->value('id');

        if ($documentId === null) {
            return;
        }

        DB::table('automation_config_versions')->insert([
            'document_id' => $documentId,
            'namespace' => $namespace,
            'scope_type' => $scopeType,
            'scope_id' => $scopeId,
            'schema_version' => 1,
            'payload' => json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
            'status' => 'valid',
            'source' => $source,
            'checksum' => $checksum,
            'changed_by' => $updatedBy,
            'changed_at' => $timestamp,
            'created_at' => $timestamp,
            'updated_at' => $timestamp,
        ]);
    }

    /**
     * @param  array<string, mixed>  $payload
     */
    private function upsertAuthorityPreset(
        string $namespace,
        string $scope,
        bool $isLocked,
        string $name,
        string $slug,
        mixed $description,
        array $payload,
        ?int $updatedBy,
        mixed $updatedAt,
    ): int {
        $timestamp = $updatedAt ?? now();
        $checksum = sha1(json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES));

        DB::table('automation_config_presets')->updateOrInsert(
            ['slug' => $slug],
            [
                'namespace' => $namespace,
                'scope' => $scope,
                'is_locked' => $isLocked,
                'name' => $name,
                'description' => $description,
                'schema_version' => 1,
                'payload' => json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
                'updated_by' => $updatedBy,
                'updated_at' => $timestamp,
                'created_at' => $timestamp,
            ]
        );

        $presetId = (int) DB::table('automation_config_presets')->where('slug', $slug)->value('id');
        DB::table('automation_config_preset_versions')->insert([
            'preset_id' => $presetId,
            'namespace' => $namespace,
            'scope' => $scope,
            'schema_version' => 1,
            'payload' => json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
            'checksum' => $checksum,
            'changed_by' => $updatedBy,
            'changed_at' => $timestamp,
            'created_at' => $timestamp,
            'updated_at' => $timestamp,
        ]);

        return $presetId;
    }

    /**
     * @return array<string, mixed>
     */
    private function decodeJsonObject(mixed $value): array
    {
        $decoded = is_array($value) ? $value : json_decode((string) $value, true);

        return is_array($decoded) ? $decoded : [];
    }

    private function normalizeProcessMode(string $mode): string
    {
        return match (trim(strtolower($mode))) {
            'tank_filling' => 'solution_fill',
            'prepare_recirculation' => 'tank_recirc',
            'irrigating', 'irrig_recirc' => 'irrigation',
            default => trim(strtolower($mode)),
        };
    }

    private function processModeToNamespace(string $mode): string
    {
        return match ($mode) {
            'generic' => AutomationConfigRegistry::NAMESPACE_ZONE_PROCESS_CALIBRATION_GENERIC,
            'solution_fill' => AutomationConfigRegistry::NAMESPACE_ZONE_PROCESS_CALIBRATION_SOLUTION_FILL,
            'tank_recirc' => AutomationConfigRegistry::NAMESPACE_ZONE_PROCESS_CALIBRATION_TANK_RECIRC,
            default => AutomationConfigRegistry::NAMESPACE_ZONE_PROCESS_CALIBRATION_IRRIGATION,
        };
    }

    private function normalizeScalarValue(mixed $value): mixed
    {
        if (! is_string($value)) {
            return $value;
        }

        $trimmed = trim($value);
        if ($trimmed === '') {
            return $value;
        }

        $normalized = strtolower($trimmed);
        if (in_array($normalized, ['true', 'false'], true)) {
            return $normalized === 'true';
        }
        if (is_numeric($trimmed)) {
            return str_contains($trimmed, '.') ? (float) $trimmed : (int) $trimmed;
        }
        if (
            (str_starts_with($trimmed, '{') && str_ends_with($trimmed, '}'))
            || (str_starts_with($trimmed, '[') && str_ends_with($trimmed, ']'))
        ) {
            $decoded = json_decode($trimmed, true);
            if (json_last_error() === JSON_ERROR_NONE) {
                return $decoded;
            }
        }

        return $value;
    }
};
