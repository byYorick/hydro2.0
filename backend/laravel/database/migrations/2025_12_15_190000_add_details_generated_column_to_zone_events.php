<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        // Основная таблица zone_events: добавляем колонку details как generated над payload_json
        if (
            Schema::hasTable('zone_events') &&
            Schema::hasColumn('zone_events', 'payload_json') &&
            !Schema::hasColumn('zone_events', 'details')
        ) {
            DB::statement(
                "ALTER TABLE zone_events ADD COLUMN details jsonb GENERATED ALWAYS AS (payload_json) STORED"
            );
        }

        // Архивная таблица удалена (Этап 5) - используем партиционирование вместо архивных таблиц
        // Код оставлен для обратной совместимости при rollback миграций
    }

    public function down(): void
    {
        if (Schema::hasTable('zone_events') && Schema::hasColumn('zone_events', 'details')) {
            DB::statement("ALTER TABLE zone_events DROP COLUMN details");
        }

        // Архивная таблица удалена (Этап 5) - код оставлен для обратной совместимости
        if (Schema::hasTable('zone_events_archive') && Schema::hasColumn('zone_events_archive', 'details')) {
            DB::statement("ALTER TABLE zone_events_archive DROP COLUMN details");
        }
    }
};
