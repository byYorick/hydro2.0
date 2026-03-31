<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('ae_tasks', function (Blueprint $table): void {
            $table->json('corr_ec_dose_sequence_json')->nullable()->after('corr_ec_amount_ml');
            $table->unsignedInteger('corr_ec_current_seq_index')->default(0)->after('corr_ec_dose_sequence_json');
        });
    }

    public function down(): void
    {
        Schema::table('ae_tasks', function (Blueprint $table): void {
            $table->dropColumn(['corr_ec_dose_sequence_json', 'corr_ec_current_seq_index']);
        });
    }
};

