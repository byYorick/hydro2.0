<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

/**
 * Дефолт zone_automation_presets.irrigation_system_type был dwc, хотя AE3
 * исполнял каплю. Строки с dwc только из этого дефолта переводятся в drip.
 *
 * Не трогаем явный каталог DWC:
 * - slug dwc-balanced, dwc-safe, dwc-aggressive;
 * - либо name/description содержит «dwc» (без учёта регистра).
 *
 * test-node-automation попадает под перевод: в сиде тип записан dwc, текст
 * профиля про HIL, не про DWC. Откат восстанавливает ровно id из журнала.
 */
return new class extends Migration
{
    private const AUDIT = 'zone_automation_preset_dwc_default_rewrites';

    public function up(): void
    {
        DB::statement("ALTER TABLE zone_automation_presets ALTER COLUMN irrigation_system_type SET DEFAULT 'drip'");

        if (! Schema::hasTable(self::AUDIT)) {
            Schema::create(self::AUDIT, function (Blueprint $table): void {
                $table->unsignedBigInteger('preset_id')->primary();
                $table->string('previous_type', 32);
                $table->timestampTz('rewritten_at')->useCurrent();
            });
        }

        $candidates = DB::select($this->candidateSql());
        $now = now();
        foreach ($candidates as $row) {
            DB::table(self::AUDIT)->updateOrInsert(
                ['preset_id' => $row->id],
                ['previous_type' => 'dwc', 'rewritten_at' => $now],
            );
            DB::table('zone_automation_presets')
                ->where('id', $row->id)
                ->update([
                    'irrigation_system_type' => 'drip',
                    'updated_at' => $now,
                ]);
        }
    }

    public function down(): void
    {
        if (Schema::hasTable(self::AUDIT)) {
            $rows = DB::table(self::AUDIT)->get();
            foreach ($rows as $row) {
                DB::table('zone_automation_presets')
                    ->where('id', $row->preset_id)
                    ->update([
                        'irrigation_system_type' => $row->previous_type,
                        'updated_at' => now(),
                    ]);
            }
            Schema::drop(self::AUDIT);
        }

        DB::statement("ALTER TABLE zone_automation_presets ALTER COLUMN irrigation_system_type SET DEFAULT 'dwc'");
    }

    private function candidateSql(): string
    {
        return <<<'SQL'
            SELECT id
            FROM zone_automation_presets
            WHERE irrigation_system_type = 'dwc'
              AND slug NOT IN ('dwc-balanced', 'dwc-safe', 'dwc-aggressive')
              AND name !~* 'dwc'
              AND COALESCE(description, '') !~* 'dwc'
              AND NOT EXISTS (
                  SELECT 1
                  FROM zone_automation_preset_dwc_default_rewrites audit
                  WHERE audit.preset_id = zone_automation_presets.id
              )
            SQL;
    }
};
