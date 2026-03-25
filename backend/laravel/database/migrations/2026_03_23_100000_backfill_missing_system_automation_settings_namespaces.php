<?php

use App\Services\SystemAutomationSettingsCatalog;
use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        if (! Schema::hasTable('system_automation_settings')) {
            return;
        }

        $existingNamespaces = DB::table('system_automation_settings')
            ->pluck('namespace')
            ->all();

        $existingNamespaceLookup = array_fill_keys($existingNamespaces, true);
        $now = now();
        $rows = [];

        foreach (SystemAutomationSettingsCatalog::allDefaults() as $namespace => $config) {
            if (isset($existingNamespaceLookup[$namespace])) {
                continue;
            }

            $rows[] = [
                'namespace' => $namespace,
                'config' => json_encode($config, JSON_THROW_ON_ERROR),
                'updated_by' => null,
                'created_at' => $now,
                'updated_at' => $now,
            ];
        }

        if ($rows !== []) {
            DB::table('system_automation_settings')->insert($rows);
        }
    }

    public function down(): void
    {
        // Legacy system_automation_settings is removed by authority cleanup.
        // Rolling this data-only backfill migration back is intentionally a no-op.
    }
};
