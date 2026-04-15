<?php

namespace App\Services;

use App\Models\ZoneConfigChange;
use Illuminate\Support\Facades\DB;

/**
 * Управляет инкрементом `zones.config_revision` и записью audit `zone_config_changes`.
 *
 * Phase 5: AE3 `BaseStageHandler._checkpoint()` сравнивает `config_revision` с
 * текущим bundle_revision и триггерит hot-reload в live-режиме при advance.
 * Без bump'а revision live-режим бесполезен — AE3 всегда видит "no change".
 */
class ZoneConfigRevisionService
{
    /**
     * Инкрементирует `zones.config_revision` и записывает `zone_config_changes`.
     * Безопасен при non-zone scope — просто no-op.
     *
     * @param  string  $scopeType  'zone' | 'system' | 'greenhouse' | 'grow_cycle'
     * @param  array  $diff  diff payload (e.g. ['fields_changed' => [...]])
     */
    public function bumpAndAudit(
        string $scopeType,
        int $scopeId,
        string $namespace,
        array $diff,
        ?int $userId,
        ?string $reason = null,
    ): ?int {
        if ($scopeType !== 'zone') {
            return null;
        }

        return DB::transaction(function () use ($scopeId, $namespace, $diff, $userId, $reason): ?int {
            // Atomic RETURNING pattern avoids read-modify-write races when two
            // concurrent PUTs race on the same zone. PostgreSQL guarantees a
            // strictly monotonic increment per row. Unique constraint
            // `zone_config_changes (zone_id, revision)` is our correctness net.
            $rows = DB::select(
                'UPDATE zones SET config_revision = COALESCE(config_revision, 0) + 1 '
                . 'WHERE id = ? RETURNING config_revision',
                [$scopeId],
            );
            if (empty($rows)) {
                return null;
            }
            $revision = (int) $rows[0]->config_revision;

            ZoneConfigChange::create([
                'zone_id' => $scopeId,
                'revision' => $revision,
                'namespace' => $namespace,
                'diff_json' => $diff,
                'user_id' => $userId,
                'reason' => $reason,
            ]);

            return $revision;
        });
    }
}
