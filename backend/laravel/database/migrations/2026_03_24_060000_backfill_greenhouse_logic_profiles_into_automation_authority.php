<?php

use App\Services\AutomationConfigRegistry;
use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        if (! Schema::hasTable('automation_config_documents') || ! Schema::hasTable('greenhouse_automation_logic_profiles')) {
            return;
        }

        $rows = DB::table('greenhouse_automation_logic_profiles')
            ->orderBy('greenhouse_id')
            ->orderBy('updated_at')
            ->orderBy('id')
            ->get()
            ->groupBy('greenhouse_id');

        foreach ($rows as $greenhouseId => $profiles) {
            $payload = $this->buildPayload($profiles->all());
            $updatedAt = $profiles->max('updated_at') ?? now();
            $updatedBy = $profiles->sortByDesc('updated_at')->first()->updated_by ?? null;
            $checksum = sha1(json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR));

            DB::table('automation_config_documents')->updateOrInsert(
                [
                    'namespace' => AutomationConfigRegistry::NAMESPACE_GREENHOUSE_LOGIC_PROFILE,
                    'scope_type' => AutomationConfigRegistry::SCOPE_GREENHOUSE,
                    'scope_id' => (int) $greenhouseId,
                ],
                [
                    'schema_version' => 1,
                    'payload' => json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR),
                    'status' => 'valid',
                    'source' => 'legacy_greenhouse_logic',
                    'checksum' => $checksum,
                    'updated_by' => $updatedBy,
                    'created_at' => $updatedAt,
                    'updated_at' => $updatedAt,
                ]
            );

            $documentId = DB::table('automation_config_documents')
                ->where('namespace', AutomationConfigRegistry::NAMESPACE_GREENHOUSE_LOGIC_PROFILE)
                ->where('scope_type', AutomationConfigRegistry::SCOPE_GREENHOUSE)
                ->where('scope_id', (int) $greenhouseId)
                ->value('id');

            if ($documentId !== null) {
                DB::table('automation_config_versions')->insert([
                    'document_id' => $documentId,
                    'namespace' => AutomationConfigRegistry::NAMESPACE_GREENHOUSE_LOGIC_PROFILE,
                    'scope_type' => AutomationConfigRegistry::SCOPE_GREENHOUSE,
                    'scope_id' => (int) $greenhouseId,
                    'schema_version' => 1,
                    'payload' => json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR),
                    'status' => 'valid',
                    'source' => 'legacy_greenhouse_logic',
                    'checksum' => $checksum,
                    'changed_by' => $updatedBy,
                    'changed_at' => $updatedAt,
                    'created_at' => now(),
                    'updated_at' => now(),
                ]);
            }
        }

        Schema::dropIfExists('greenhouse_automation_logic_profiles');
    }

    public function down(): void
    {
        // Legacy table intentionally not restored.
    }

    /**
     * @param  array<int, object>  $profiles
     * @return array<string, mixed>
     */
    private function buildPayload(array $profiles): array
    {
        $allowedModes = ['setup', 'working'];
        $serializedProfiles = [];
        $activeMode = null;
        $latestActiveTimestamp = null;

        foreach ($profiles as $profile) {
            $mode = (string) ($profile->mode ?? '');
            if (! in_array($mode, $allowedModes, true)) {
                continue;
            }

            $subsystems = is_array($profile->subsystems)
                ? $profile->subsystems
                : json_decode((string) ($profile->subsystems ?? '{}'), true);
            if (! is_array($subsystems) || array_is_list($subsystems)) {
                $subsystems = [];
            }

            $serializedProfiles[$mode] = [
                'mode' => $mode,
                'is_active' => (bool) ($profile->is_active ?? false),
                'subsystems' => $subsystems,
                'updated_at' => $profile->updated_at,
                'created_at' => $profile->created_at,
                'updated_by' => $profile->updated_by ?? null,
                'created_by' => $profile->created_by ?? null,
            ];

            if ((bool) ($profile->is_active ?? false)) {
                $timestamp = strtotime((string) ($profile->updated_at ?? $profile->created_at ?? '')) ?: 0;
                if ($latestActiveTimestamp === null || $timestamp >= $latestActiveTimestamp) {
                    $latestActiveTimestamp = $timestamp;
                    $activeMode = $mode;
                }
            }
        }

        return [
            'active_mode' => $activeMode,
            'profiles' => $serializedProfiles,
        ];
    }
};
