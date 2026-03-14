<?php

use App\Services\SystemAutomationSettingsCatalog;
use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('system_automation_settings', function (Blueprint $table): void {
            $table->id();
            $table->string('namespace', 64)->unique();
            $table->jsonb('config')->default(DB::raw("'{}'::jsonb"));
            $table->foreignId('updated_by')->nullable()->constrained('users')->nullOnDelete();
            $table->timestamps();
        });

        $now = now();
        $rows = [];
        foreach (SystemAutomationSettingsCatalog::allDefaults() as $namespace => $config) {
            $rows[] = [
                'namespace' => $namespace,
                'config' => json_encode($config, JSON_THROW_ON_ERROR),
                'updated_by' => null,
                'created_at' => $now,
                'updated_at' => $now,
            ];
        }

        if ($rows !== []) {
            DB::table('system_automation_settings')->insert($rows);
        }
    }

    public function down(): void
    {
        Schema::dropIfExists('system_automation_settings');
    }
};
