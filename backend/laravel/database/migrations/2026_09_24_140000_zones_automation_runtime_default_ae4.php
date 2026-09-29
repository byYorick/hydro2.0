<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Default automation_runtime для новых зон — ae4.
 * Живые строки не обновляются массово (волна 10).
 */
return new class extends Migration
{
    public function up(): void
    {
        DB::statement("ALTER TABLE zones ALTER COLUMN automation_runtime SET DEFAULT 'ae4'");
    }

    public function down(): void
    {
        DB::statement("ALTER TABLE zones ALTER COLUMN automation_runtime SET DEFAULT 'ae3'");
    }
};
