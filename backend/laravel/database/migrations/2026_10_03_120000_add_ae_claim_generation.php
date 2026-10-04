<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        if (Schema::hasTable('ae_tasks')) {
            Schema::table('ae_tasks', function (Blueprint $table): void {
                if (! Schema::hasColumn('ae_tasks', 'claim_generation')) {
                    $table->unsignedBigInteger('claim_generation')->default(0);
                }
                if (! Schema::hasColumn('ae_tasks', 'process_run_id')) {
                    $table->string('process_run_id', 64)->nullable();
                }
            });
        }

        if (Schema::hasTable('ae_zone_leases')) {
            Schema::table('ae_zone_leases', function (Blueprint $table): void {
                if (! Schema::hasColumn('ae_zone_leases', 'claim_generation')) {
                    $table->unsignedBigInteger('claim_generation')->default(0);
                }
                if (! Schema::hasColumn('ae_zone_leases', 'process_run_id')) {
                    $table->string('process_run_id', 64)->nullable();
                }
            });
        }
    }

    public function down(): void
    {
        if (Schema::hasTable('ae_zone_leases')) {
            Schema::table('ae_zone_leases', function (Blueprint $table): void {
                if (Schema::hasColumn('ae_zone_leases', 'process_run_id')) {
                    $table->dropColumn('process_run_id');
                }
                if (Schema::hasColumn('ae_zone_leases', 'claim_generation')) {
                    $table->dropColumn('claim_generation');
                }
            });
        }

        if (Schema::hasTable('ae_tasks')) {
            Schema::table('ae_tasks', function (Blueprint $table): void {
                if (Schema::hasColumn('ae_tasks', 'process_run_id')) {
                    $table->dropColumn('process_run_id');
                }
                if (Schema::hasColumn('ae_tasks', 'claim_generation')) {
                    $table->dropColumn('claim_generation');
                }
            });
        }
    }
};
