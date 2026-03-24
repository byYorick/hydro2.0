<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

/**
 * AE3 cutover:
 *  1. Нормализовать все legacy/null runtime значения к ae3 и сделать ae3 DEFAULT.
 *  2. Добавить колонку zones.control_mode с CHECK constraint.
 *
 * @see .qoder/specs/ae3-manual-mode-full-migration-plan.md §3.1 Этап 0
 */
return new class extends Migration
{
    public function up(): void
    {
        // 1. Добавить control_mode в zones (если ещё нет)
        if (Schema::hasTable('zones') && ! Schema::hasColumn('zones', 'control_mode')) {
            DB::statement("
                ALTER TABLE zones
                ADD COLUMN control_mode VARCHAR(16) NOT NULL DEFAULT 'auto'
            ");
            DB::statement("
                ALTER TABLE zones
                ADD CONSTRAINT zones_control_mode_check
                CHECK (control_mode IN ('auto', 'semi', 'manual'))
            ");
        }

        // 2. Нормализовать legacy/null runtime значения к ae3
        DB::statement("
            UPDATE zones
            SET automation_runtime = 'ae3'
            WHERE automation_runtime IS NULL
              OR automation_runtime = ''
        ");

        // 3. Сменить DEFAULT на ae3
        DB::statement("
            ALTER TABLE zones
            ALTER COLUMN automation_runtime SET DEFAULT 'ae3'
        ");

        // 4. Заменить CHECK constraint (только ae3 допустим)
        DB::statement('ALTER TABLE zones DROP CONSTRAINT IF EXISTS zones_automation_runtime_check');
        DB::statement("
            ALTER TABLE zones
            ADD CONSTRAINT zones_automation_runtime_check
            CHECK (automation_runtime IN ('ae3'))
        ");
    }

    public function down(): void
    {
        // Оставить ae3 единственным допустимым runtime и удалить только control_mode.
        DB::statement('ALTER TABLE zones DROP CONSTRAINT IF EXISTS zones_automation_runtime_check');
        DB::statement("
            ALTER TABLE zones
            ADD CONSTRAINT zones_automation_runtime_check
            CHECK (automation_runtime IN ('ae3'))
        ");

        // Восстановить DEFAULT
        DB::statement("
            ALTER TABLE zones
            ALTER COLUMN automation_runtime SET DEFAULT 'ae3'
        ");

        // Удалить control_mode
        if (Schema::hasColumn('zones', 'control_mode')) {
            DB::statement('ALTER TABLE zones DROP CONSTRAINT IF EXISTS zones_control_mode_check');
            DB::statement('ALTER TABLE zones DROP COLUMN IF EXISTS control_mode');
        }
    }
};
