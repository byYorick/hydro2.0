<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Добавить поля ручного режима в ae_tasks:
 *  - pending_manual_step  — шаг, ожидающий исполнения (например 'clean_fill_stop')
 *  - control_mode_snapshot — снимок control_mode на момент создания/обновления задачи
 *
 * @see .qoder/specs/ae3-manual-mode-full-migration-plan.md §3.1 Этап 0.2
 */
return new class extends Migration
{
    public function up(): void
    {
        if (! Schema::hasTable('ae_tasks')) {
            return;
        }

        Schema::table('ae_tasks', function (Blueprint $table) {
            if (! Schema::hasColumn('ae_tasks', 'pending_manual_step')) {
                $table->string('pending_manual_step', 64)->nullable()->after('corr_wait_until');
            }
            if (! Schema::hasColumn('ae_tasks', 'control_mode_snapshot')) {
                $table->string('control_mode_snapshot', 16)->nullable()->after('pending_manual_step');
            }
        });
    }

    public function down(): void
    {
        if (! Schema::hasTable('ae_tasks')) {
            return;
        }

        Schema::table('ae_tasks', function (Blueprint $table) {
            $table->dropColumn(array_filter([
                Schema::hasColumn('ae_tasks', 'control_mode_snapshot') ? 'control_mode_snapshot' : null,
                Schema::hasColumn('ae_tasks', 'pending_manual_step') ? 'pending_manual_step' : null,
            ]));
        });
    }
};
