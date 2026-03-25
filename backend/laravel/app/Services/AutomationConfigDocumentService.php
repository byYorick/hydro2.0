<?php

namespace App\Services;

use App\Models\AutomationConfigDocument;
use App\Models\AutomationConfigVersion;
use App\Support\Automation\ZoneCorrectionResolvedConfigBuilder;
use App\Support\Automation\ZoneLogicProfileNormalizer;
use Illuminate\Support\Facades\DB;

class AutomationConfigDocumentService
{
    public function __construct(
        private readonly AutomationConfigRegistry $registry,
        private readonly ZoneLogicProfileNormalizer $logicProfileNormalizer,
        private readonly ZoneCorrectionResolvedConfigBuilder $zoneCorrectionResolvedConfigBuilder,
    ) {
    }

    public function getDocument(string $namespace, string $scopeType, int $scopeId, bool $materialize = true): ?AutomationConfigDocument
    {
        $document = AutomationConfigDocument::query()
            ->where('namespace', $namespace)
            ->where('scope_type', $scopeType)
            ->where('scope_id', $scopeId)
            ->first();

        if ($document || ! $materialize) {
            return $document;
        }

        return $this->materializeDefaultDocument($namespace, $scopeType, $scopeId);
    }

    /**
     * @return array<string, mixed>
     */
    public function getPayload(string $namespace, string $scopeType, int $scopeId, bool $materialize = true): array
    {
        $document = $this->getDocument($namespace, $scopeType, $scopeId, $materialize);
        $payload = $document?->payload;

        return is_array($payload) && (! array_is_list($payload) || $payload === [])
            ? $payload
            : $this->registry->defaultPayload($namespace);
    }

    /**
     * @return array<int, mixed>
     */
    public function getListPayload(string $namespace, string $scopeType, int $scopeId, bool $materialize = true): array
    {
        $document = $this->getDocument($namespace, $scopeType, $scopeId, $materialize);
        $payload = $document?->payload;

        return is_array($payload) && array_is_list($payload) ? $payload : [];
    }

    /**
     * @return array<string, mixed>
     */
    public function getSystemPayloadByLegacyNamespace(string $legacyNamespace, bool $materialize = true): array
    {
        $authorityNamespace = $this->registry->legacySystemNamespaceToAuthority($legacyNamespace);
        if (! is_string($authorityNamespace) || $authorityNamespace === '') {
            throw new \InvalidArgumentException("Unknown legacy system namespace {$legacyNamespace}.");
        }

        return $this->getPayload($authorityNamespace, AutomationConfigRegistry::SCOPE_SYSTEM, 0, $materialize);
    }

    public function upsertDocument(
        string $namespace,
        string $scopeType,
        int $scopeId,
        array $payload,
        ?int $userId = null,
        string $source = 'api'
    ): AutomationConfigDocument {
        $expectedScopeType = $this->registry->scopeType($namespace);
        if ($scopeType !== $expectedScopeType) {
            throw new \InvalidArgumentException("Namespace {$namespace} must be stored in scope {$expectedScopeType}.");
        }

        $normalizedPayload = $this->normalizePayload($namespace, $payload);
        $this->registry->validate($namespace, $normalizedPayload);

        return DB::transaction(function () use ($namespace, $scopeType, $scopeId, $normalizedPayload, $userId, $source): AutomationConfigDocument {
            $checksum = $this->checksum($normalizedPayload);
            $document = AutomationConfigDocument::query()->firstOrNew([
                'namespace' => $namespace,
                'scope_type' => $scopeType,
                'scope_id' => $scopeId,
            ]);

            $document->schema_version = $this->registry->schemaVersion($namespace);
            $document->payload = $normalizedPayload;
            $document->status = 'valid';
            $document->source = $source;
            $document->checksum = $checksum;
            $document->updated_by = $userId;
            $document->save();

            AutomationConfigVersion::query()->create([
                'document_id' => $document->id,
                'namespace' => $namespace,
                'scope_type' => $scopeType,
                'scope_id' => $scopeId,
                'schema_version' => $document->schema_version,
                'payload' => $normalizedPayload,
                'status' => 'valid',
                'source' => $source,
                'checksum' => $checksum,
                'changed_by' => $userId,
                'changed_at' => now(),
            ]);

            app(AutomationConfigCompiler::class)->compileAffectedScopes($scopeType, $scopeId);

            return $document->fresh();
        });
    }

    public function ensureSystemDefaults(): void
    {
        foreach ($this->registry->requiredNamespacesForScope(AutomationConfigRegistry::SCOPE_SYSTEM) as $namespace) {
            $this->materializeDefaultDocument($namespace, AutomationConfigRegistry::SCOPE_SYSTEM, 0);
        }
        app(AutomationConfigCompiler::class)->compileSystemBundle();
    }

    public function ensureZoneDefaults(int $zoneId): void
    {
        foreach ($this->registry->requiredNamespacesForScope(AutomationConfigRegistry::SCOPE_ZONE) as $namespace) {
            $this->materializeDefaultDocument($namespace, AutomationConfigRegistry::SCOPE_ZONE, $zoneId);
        }

        app(AutomationConfigCompiler::class)->compileZoneBundle($zoneId);
    }

    /**
     * @param  array<string, array<string, mixed>>  $documentsByNamespace
     */
    public function upsertCycleDocuments(int $growCycleId, array $documentsByNamespace, ?int $userId = null): void
    {
        foreach ($documentsByNamespace as $namespace => $payload) {
            $this->upsertDocument($namespace, AutomationConfigRegistry::SCOPE_GROW_CYCLE, $growCycleId, $payload, $userId, 'cycle_start');
        }
    }

    public function ensureCycleDefaults(int $growCycleId): void
    {
        foreach ($this->registry->requiredNamespacesForScope(AutomationConfigRegistry::SCOPE_GROW_CYCLE) as $namespace) {
            $this->materializeDefaultDocument($namespace, AutomationConfigRegistry::SCOPE_GROW_CYCLE, $growCycleId);
        }
    }

    public function materializeDefaultDocument(string $namespace, string $scopeType, int $scopeId): AutomationConfigDocument
    {
        $document = AutomationConfigDocument::query()->firstOrNew([
            'namespace' => $namespace,
            'scope_type' => $scopeType,
            'scope_id' => $scopeId,
        ]);

        if ($document->exists) {
            return $document;
        }

        $payload = $this->normalizePayload($namespace, $this->registry->defaultPayload($namespace));
        $checksum = $this->checksum($payload);

        $document->schema_version = $this->registry->schemaVersion($namespace);
        $document->payload = $payload;
        $document->status = 'valid';
        $document->source = 'bootstrap';
        $document->checksum = $checksum;
        $document->updated_by = null;
        $document->save();

        AutomationConfigVersion::query()->create([
            'document_id' => $document->id,
            'namespace' => $namespace,
            'scope_type' => $scopeType,
            'scope_id' => $scopeId,
            'schema_version' => $document->schema_version,
            'payload' => $payload,
            'status' => 'valid',
            'source' => 'bootstrap',
            'checksum' => $checksum,
            'changed_by' => null,
            'changed_at' => now(),
        ]);

        return $document;
    }

    /**
     * @return array<string, mixed>
     */
    public function normalizePayload(string $namespace, array $payload): array
    {
        if ($payload !== [] && array_is_list($payload) && $namespace !== AutomationConfigRegistry::NAMESPACE_CYCLE_MANUAL_OVERRIDES) {
            throw new \InvalidArgumentException("Payload for {$namespace} must be an object.");
        }

        return match ($namespace) {
            AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION => $this->normalizeZoneCorrectionPayload($payload),
            AutomationConfigRegistry::NAMESPACE_GREENHOUSE_LOGIC_PROFILE => $this->normalizeGreenhouseLogicProfilePayload($payload),
            AutomationConfigRegistry::NAMESPACE_ZONE_LOGIC_PROFILE => $this->normalizeLogicProfilePayload($payload),
            default => $payload,
        };
    }

    /**
     * @return array<string, mixed>
     */
    private function normalizeZoneCorrectionPayload(array $payload): array
    {
        return [
            'preset_id' => isset($payload['preset_id']) ? (int) $payload['preset_id'] : null,
            'base_config' => is_array($payload['base_config'] ?? null) && ! array_is_list($payload['base_config'])
                ? $payload['base_config']
                : ZoneCorrectionConfigCatalog::defaults(),
            'phase_overrides' => is_array($payload['phase_overrides'] ?? null) && ! array_is_list($payload['phase_overrides'])
                ? $payload['phase_overrides']
                : [],
            'resolved_config' => $this->zoneCorrectionResolvedConfigBuilder->buildFromPayload($payload),
            'last_applied_at' => $payload['last_applied_at'] ?? null,
            'last_applied_version' => isset($payload['last_applied_version']) ? (int) $payload['last_applied_version'] : null,
        ];
    }

    /**
     * @return array<string, mixed>
     */
    private function normalizeLogicProfilePayload(array $payload): array
    {
        $profiles = is_array($payload['profiles'] ?? null) && ! array_is_list($payload['profiles'])
            ? $payload['profiles']
            : [];
        $normalizedProfiles = [];

        foreach ($profiles as $mode => $profile) {
            if (! is_string($mode) || ! is_array($profile) || array_is_list($profile)) {
                continue;
            }

            $normalizedProfiles[$mode] = $this->logicProfileNormalizer->normalizeProfile(
                $mode,
                $profile,
                'automation_logic_profile_document_normalized'
            );
        }

        $activeMode = isset($payload['active_mode']) && is_string($payload['active_mode'])
            ? $payload['active_mode']
            : null;

        return [
            'active_mode' => $activeMode,
            'profiles' => $normalizedProfiles,
        ];
    }

    /**
     * @return array<string, mixed>
     */
    private function normalizeGreenhouseLogicProfilePayload(array $payload): array
    {
        $profiles = is_array($payload['profiles'] ?? null) && ! array_is_list($payload['profiles'])
            ? $payload['profiles']
            : [];
        $activeMode = isset($payload['active_mode']) && is_string($payload['active_mode'])
            ? $payload['active_mode']
            : null;
        $normalizedProfiles = [];

        foreach ($profiles as $mode => $profile) {
            if (! is_string($mode) || ! is_array($profile) || array_is_list($profile)) {
                continue;
            }

            $subsystems = is_array($profile['subsystems'] ?? null) && ! array_is_list($profile['subsystems'])
                ? $profile['subsystems']
                : [];
            $climate = is_array($subsystems['climate'] ?? null) && ! array_is_list($subsystems['climate'])
                ? $subsystems['climate']
                : ['enabled' => false];
            $execution = is_array($climate['execution'] ?? null) && ! array_is_list($climate['execution'])
                ? $climate['execution']
                : [];

            $normalizedProfiles[$mode] = [
                'mode' => $mode,
                'is_active' => $mode === $activeMode,
                'subsystems' => [
                    'climate' => [
                        'enabled' => (bool) ($climate['enabled'] ?? false),
                        'execution' => $execution,
                    ],
                ],
                'updated_at' => $profile['updated_at'] ?? null,
                'created_at' => $profile['created_at'] ?? null,
                'updated_by' => $profile['updated_by'] ?? null,
                'created_by' => $profile['created_by'] ?? null,
            ];
        }

        return [
            'active_mode' => $activeMode,
            'profiles' => $normalizedProfiles,
        ];
    }

    /**
     * @param  array<string, mixed>  $payload
     */
    public function checksum(array $payload): string
    {
        return sha1(json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR));
    }
}
