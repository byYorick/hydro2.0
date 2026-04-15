<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('zones', function (Blueprint $table) {
            $table->string('config_mode', 16)->default('locked');
            $table->timestamp('config_mode_changed_at')->nullable();
            $table->foreignId('config_mode_changed_by')->nullable()->constrained('users');
            $table->timestamp('live_until')->nullable();
            $table->timestamp('live_started_at')->nullable();
            $table->unsignedBigInteger('config_revision')->default(1);
        });

        DB::statement(
            "ALTER TABLE zones ADD CONSTRAINT zones_config_mode_check "
            . "CHECK (config_mode IN ('locked','live'))"
        );
        DB::statement(
            "ALTER TABLE zones ADD CONSTRAINT zones_live_requires_until "
            . "CHECK (config_mode = 'locked' OR live_until IS NOT NULL)"
        );

        Schema::create('zone_config_changes', function (Blueprint $table) {
            $table->id();
            $table->foreignId('zone_id')->constrained()->cascadeOnDelete();
            $table->unsignedBigInteger('revision');
            $table->string('namespace', 64);
            $table->jsonb('diff_json');
            $table->foreignId('user_id')->nullable()->constrained('users');
            $table->text('reason')->nullable();
            $table->timestamp('created_at')->useCurrent();
            $table->unique(['zone_id', 'revision']);
            $table->index(['zone_id', 'created_at']);
            $table->index(['zone_id', 'namespace']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('zone_config_changes');

        DB::statement('ALTER TABLE zones DROP CONSTRAINT IF EXISTS zones_live_requires_until');
        DB::statement('ALTER TABLE zones DROP CONSTRAINT IF EXISTS zones_config_mode_check');

        Schema::table('zones', function (Blueprint $table) {
            $table->dropForeign(['config_mode_changed_by']);
            $table->dropColumn([
                'config_mode',
                'config_mode_changed_at',
                'config_mode_changed_by',
                'live_until',
                'live_started_at',
                'config_revision',
            ]);
        });
    }
};
