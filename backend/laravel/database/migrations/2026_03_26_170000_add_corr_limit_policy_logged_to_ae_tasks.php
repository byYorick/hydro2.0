<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        if (! Schema::hasTable('ae_tasks') || Schema::hasColumn('ae_tasks', 'corr_limit_policy_logged')) {
            return;
        }

        Schema::table('ae_tasks', function (Blueprint $table): void {
            $table->boolean('corr_limit_policy_logged')
                ->default(false)
                ->after('corr_ph_amount_ml');
        });
    }

    public function down(): void
    {
        if (! Schema::hasTable('ae_tasks') || ! Schema::hasColumn('ae_tasks', 'corr_limit_policy_logged')) {
            return;
        }

        Schema::table('ae_tasks', function (Blueprint $table): void {
            $table->dropColumn('corr_limit_policy_logged');
        });
    }
};
