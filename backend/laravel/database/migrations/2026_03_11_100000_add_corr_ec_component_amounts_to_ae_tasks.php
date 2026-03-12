<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        if (! Schema::hasTable('ae_tasks')) {
            return;
        }

        Schema::table('ae_tasks', function (Blueprint $table) {
            if (! Schema::hasColumn('ae_tasks', 'corr_ec_component')) {
                $table->string('corr_ec_component', 100)->nullable()->after('corr_wait_until');
            }
            if (! Schema::hasColumn('ae_tasks', 'corr_ec_amount_ml')) {
                $table->float('corr_ec_amount_ml')->nullable()->after('corr_ec_component');
            }
            if (! Schema::hasColumn('ae_tasks', 'corr_ph_amount_ml')) {
                $table->float('corr_ph_amount_ml')->nullable()->after('corr_ec_amount_ml');
            }
        });
    }

    public function down(): void
    {
        if (! Schema::hasTable('ae_tasks')) {
            return;
        }

        Schema::table('ae_tasks', function (Blueprint $table) {
            $columns = array_values(array_filter([
                Schema::hasColumn('ae_tasks', 'corr_ph_amount_ml') ? 'corr_ph_amount_ml' : null,
                Schema::hasColumn('ae_tasks', 'corr_ec_amount_ml') ? 'corr_ec_amount_ml' : null,
                Schema::hasColumn('ae_tasks', 'corr_ec_component') ? 'corr_ec_component' : null,
            ]));

            if ($columns !== []) {
                $table->dropColumn($columns);
            }
        });
    }
};
