<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('sensor_calibrations', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('zone_id')->constrained('zones')->cascadeOnDelete();
            $table->foreignId('node_channel_id')->constrained('node_channels')->cascadeOnDelete();
            $table->string('sensor_type', 16);
            $table->string('status', 32)->default('started');

            $table->decimal('point_1_reference', 12, 4)->nullable();
            $table->string('point_1_command_id', 128)->nullable();
            $table->timestampTz('point_1_sent_at')->nullable();
            $table->string('point_1_result', 16)->nullable();
            $table->text('point_1_error')->nullable();

            $table->decimal('point_2_reference', 12, 4)->nullable();
            $table->string('point_2_command_id', 128)->nullable();
            $table->timestampTz('point_2_sent_at')->nullable();
            $table->string('point_2_result', 16)->nullable();
            $table->text('point_2_error')->nullable();

            $table->timestampTz('completed_at')->nullable();
            $table->foreignId('calibrated_by')->nullable()->constrained('users')->nullOnDelete();
            $table->text('notes')->nullable();
            $table->jsonb('meta')->default(DB::raw("'{}'::jsonb"));
            $table->timestamps();

            $table->index(['zone_id', 'sensor_type', 'created_at'], 'idx_sensor_cal_zone_type_created');
            $table->index(['node_channel_id', 'status', 'created_at'], 'idx_sensor_cal_channel_status_created');
            $table->unique(['node_channel_id', 'point_1_command_id'], 'uniq_sensor_cal_point1_cmd');
            $table->unique(['node_channel_id', 'point_2_command_id'], 'uniq_sensor_cal_point2_cmd');
        });

        DB::statement(<<<'SQL'
            ALTER TABLE sensor_calibrations
            ADD CONSTRAINT chk_sensor_calibrations_sensor_type
            CHECK (sensor_type IN ('ph', 'ec'))
        SQL);

        DB::statement(<<<'SQL'
            ALTER TABLE sensor_calibrations
            ADD CONSTRAINT chk_sensor_calibrations_status
            CHECK (status IN (
                'started',
                'point_1_pending',
                'point_1_done',
                'point_2_pending',
                'completed',
                'failed',
                'cancelled'
            ))
        SQL);

        DB::statement(<<<'SQL'
            CREATE UNIQUE INDEX uniq_sensor_cal_active_channel
            ON sensor_calibrations (node_channel_id)
            WHERE status NOT IN ('completed', 'failed', 'cancelled')
        SQL);
    }

    public function down(): void
    {
        Schema::dropIfExists('sensor_calibrations');
    }
};
