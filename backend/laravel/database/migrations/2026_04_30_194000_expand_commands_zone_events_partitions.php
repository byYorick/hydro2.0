<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    public function up(): void
    {
        if (DB::getDriverName() !== 'pgsql') {
            return;
        }

        $this->ensureMonthlyPartitions('commands');
        $this->ensureMonthlyPartitions('zone_events');
    }

    public function down(): void
    {
        // Партиции intentionally сохраняем: откат не удаляет рабочие historical partitions.
    }

    private function ensureMonthlyPartitions(string $table): void
    {
        $isPartitioned = DB::selectOne(
            "SELECT EXISTS (SELECT 1 FROM pg_partitioned_table WHERE partrelid = '{$table}'::regclass) AS exists"
        );

        if (! ($isPartitioned->exists ?? false)) {
            return;
        }

        $start = now()->startOfMonth();

        for ($i = -24; $i <= 24; $i++) {
            $from = $start->copy()->addMonths($i);
            $to = $from->copy()->addMonth();
            $partition = sprintf('%s_partitioned_%s', $table, $from->format('Y_m'));

            DB::statement(
                "CREATE TABLE IF NOT EXISTS {$partition} PARTITION OF {$table} FOR VALUES FROM ('{$from->toDateString()}') TO ('{$to->toDateString()}')"
            );
        }
    }
};
