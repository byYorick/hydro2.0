<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        $this->upgradeAeTaskDosePrecision();
        $this->addPumpCalibrationMlPerSecCheck();
        $this->deduplicateActiveProcessCalibrations();
        $this->addOneActiveProcessCalibrationIndex();
    }

    public function down(): void
    {
        $this->dropOneActiveProcessCalibrationIndex();
        $this->dropPumpCalibrationMlPerSecCheck();
        $this->downgradeAeTaskDosePrecision();
    }

    private function upgradeAeTaskDosePrecision(): void
    {
        if (! Schema::hasTable('ae_tasks') || DB::getDriverName() !== 'pgsql') {
            return;
        }

        if (Schema::hasColumn('ae_tasks', 'corr_ec_amount_ml')) {
            DB::statement(
                'ALTER TABLE ae_tasks ALTER COLUMN corr_ec_amount_ml TYPE NUMERIC(12,3) USING ROUND(corr_ec_amount_ml::numeric, 3)'
            );
        }

        if (Schema::hasColumn('ae_tasks', 'corr_ph_amount_ml')) {
            DB::statement(
                'ALTER TABLE ae_tasks ALTER COLUMN corr_ph_amount_ml TYPE NUMERIC(12,3) USING ROUND(corr_ph_amount_ml::numeric, 3)'
            );
        }
    }

    private function downgradeAeTaskDosePrecision(): void
    {
        if (! Schema::hasTable('ae_tasks') || DB::getDriverName() !== 'pgsql') {
            return;
        }

        if (Schema::hasColumn('ae_tasks', 'corr_ec_amount_ml')) {
            DB::statement('ALTER TABLE ae_tasks ALTER COLUMN corr_ec_amount_ml TYPE DOUBLE PRECISION');
        }

        if (Schema::hasColumn('ae_tasks', 'corr_ph_amount_ml')) {
            DB::statement('ALTER TABLE ae_tasks ALTER COLUMN corr_ph_amount_ml TYPE DOUBLE PRECISION');
        }
    }

    private function addPumpCalibrationMlPerSecCheck(): void
    {
        if (! Schema::hasTable('pump_calibrations') || DB::getDriverName() !== 'pgsql') {
            return;
        }

        DB::statement(
            <<<'SQL'
            DO $$
            BEGIN
                ALTER TABLE pump_calibrations
                ADD CONSTRAINT pump_calibrations_ml_per_sec_runtime_bounds_check
                CHECK (ml_per_sec >= 0.01 AND ml_per_sec <= 100.0);
            EXCEPTION
                WHEN duplicate_object THEN NULL;
            END $$;
            SQL
        );
    }

    private function dropPumpCalibrationMlPerSecCheck(): void
    {
        if (! Schema::hasTable('pump_calibrations') || DB::getDriverName() !== 'pgsql') {
            return;
        }

        DB::statement(
            'ALTER TABLE pump_calibrations DROP CONSTRAINT IF EXISTS pump_calibrations_ml_per_sec_runtime_bounds_check'
        );
    }

    private function deduplicateActiveProcessCalibrations(): void
    {
        if (! Schema::hasTable('zone_process_calibrations')) {
            return;
        }

        $duplicates = DB::table('zone_process_calibrations')
            ->select('zone_id', 'mode', DB::raw('MAX(id) AS keep_id'))
            ->where('is_active', true)
            ->groupBy('zone_id', 'mode')
            ->havingRaw('COUNT(*) > 1')
            ->get();

        $now = now();

        foreach ($duplicates as $duplicate) {
            DB::table('zone_process_calibrations')
                ->where('zone_id', $duplicate->zone_id)
                ->where('mode', $duplicate->mode)
                ->where('is_active', true)
                ->where('id', '<>', $duplicate->keep_id)
                ->update([
                    'is_active' => false,
                    'valid_to' => $now,
                    'updated_at' => $now,
                ]);
        }
    }

    private function addOneActiveProcessCalibrationIndex(): void
    {
        if (! Schema::hasTable('zone_process_calibrations')) {
            return;
        }

        $driver = DB::getDriverName();
        if ($driver === 'pgsql') {
            DB::statement(
                'CREATE UNIQUE INDEX IF NOT EXISTS zone_process_calibrations_one_active_mode_unique
                 ON zone_process_calibrations(zone_id, mode)
                 WHERE is_active = TRUE'
            );

            return;
        }

        if ($driver === 'sqlite') {
            DB::statement(
                'CREATE UNIQUE INDEX IF NOT EXISTS zone_process_calibrations_one_active_mode_unique
                 ON zone_process_calibrations(zone_id, mode)
                 WHERE is_active = 1'
            );
        }
    }

    private function dropOneActiveProcessCalibrationIndex(): void
    {
        if (! Schema::hasTable('zone_process_calibrations')) {
            return;
        }

        DB::statement('DROP INDEX IF EXISTS zone_process_calibrations_one_active_mode_unique');
    }
};
