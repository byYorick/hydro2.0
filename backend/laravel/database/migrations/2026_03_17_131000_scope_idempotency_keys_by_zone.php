<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        $this->scopeZoneAutomationIntentKeys();
        $this->scopeAeTaskKeys();
    }

    public function down(): void
    {
        $this->restoreZoneAutomationIntentKeyScope();
        $this->restoreAeTaskKeyScope();
    }

    private function scopeZoneAutomationIntentKeys(): void
    {
        if (! Schema::hasTable('zone_automation_intents')) {
            return;
        }

        if (DB::getDriverName() === 'pgsql') {
            $this->dropPgUniqueArtifact('zone_automation_intents', 'zone_automation_intents_idempotency_key_unique');
            DB::statement(
                'CREATE UNIQUE INDEX IF NOT EXISTS zone_automation_intents_zone_idempotency_unique
                 ON zone_automation_intents(zone_id, idempotency_key)'
            );

            return;
        }

        Schema::table('zone_automation_intents', function (Blueprint $table) {
            $table->dropUnique('zone_automation_intents_idempotency_key_unique');
            $table->unique(['zone_id', 'idempotency_key'], 'zone_automation_intents_zone_idempotency_unique');
        });
    }

    private function restoreZoneAutomationIntentKeyScope(): void
    {
        if (! Schema::hasTable('zone_automation_intents')) {
            return;
        }

        if (DB::getDriverName() === 'pgsql') {
            $this->dropPgUniqueArtifact('zone_automation_intents', 'zone_automation_intents_zone_idempotency_unique');
            DB::statement(
                'CREATE UNIQUE INDEX IF NOT EXISTS zone_automation_intents_idempotency_key_unique
                 ON zone_automation_intents(idempotency_key)'
            );

            return;
        }

        Schema::table('zone_automation_intents', function (Blueprint $table) {
            $table->dropUnique('zone_automation_intents_zone_idempotency_unique');
            $table->unique('idempotency_key', 'zone_automation_intents_idempotency_key_unique');
        });
    }

    private function scopeAeTaskKeys(): void
    {
        if (! Schema::hasTable('ae_tasks')) {
            return;
        }

        if (DB::getDriverName() === 'pgsql') {
            $this->dropPgUniqueArtifact('ae_tasks', 'ae_tasks_idempotency_key_unique');
            DB::statement(
                'CREATE UNIQUE INDEX IF NOT EXISTS ae_tasks_zone_idempotency_unique
                 ON ae_tasks(zone_id, idempotency_key)'
            );

            return;
        }

        Schema::table('ae_tasks', function (Blueprint $table) {
            $table->dropUnique('ae_tasks_idempotency_key_unique');
            $table->unique(['zone_id', 'idempotency_key'], 'ae_tasks_zone_idempotency_unique');
        });
    }

    private function restoreAeTaskKeyScope(): void
    {
        if (! Schema::hasTable('ae_tasks')) {
            return;
        }

        if (DB::getDriverName() === 'pgsql') {
            $this->dropPgUniqueArtifact('ae_tasks', 'ae_tasks_zone_idempotency_unique');
            DB::statement(
                'CREATE UNIQUE INDEX IF NOT EXISTS ae_tasks_idempotency_key_unique
                 ON ae_tasks(idempotency_key)'
            );

            return;
        }

        Schema::table('ae_tasks', function (Blueprint $table) {
            $table->dropUnique('ae_tasks_zone_idempotency_unique');
            $table->unique('idempotency_key', 'ae_tasks_idempotency_key_unique');
        });
    }

    private function dropPgUniqueArtifact(string $table, string $name): void
    {
        DB::statement(sprintf('ALTER TABLE %s DROP CONSTRAINT IF EXISTS %s', $table, $name));
        DB::statement(sprintf('DROP INDEX IF EXISTS %s', $name));
    }
};
