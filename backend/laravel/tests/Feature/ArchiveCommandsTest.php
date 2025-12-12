<?php

namespace Tests\Feature;

use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\DB;
use Tests\TestCase;
use App\Models\Command;
use App\Models\CommandsArchive;
use Carbon\Carbon;

class ArchiveCommandsTest extends TestCase
{
    use RefreshDatabase;

    /**
     * Тест архивирования команд с chunking для предотвращения утечки памяти.
     */
    public function test_archive_commands_uses_chunking(): void
    {
        // Создаем необходимые зависимости
        $zone = \App\Models\Zone::factory()->create();
        $node = \App\Models\DeviceNode::factory()->create(['zone_id' => $zone->id]);
        
        // Создаем старые команды для архивирования
        $oldDate = Carbon::now()->subDays(95);
        
        // Создаем 1500 старых команд (больше чем размер чанка 500)
        for ($i = 0; $i < 1500; $i++) {
            DB::table('commands')->insert([
                'zone_id' => $zone->id,
                'node_id' => $node->id,
                'channel' => 'ph_pump',
                'cmd' => 'run_pump',
                'params' => json_encode(['duration_ms' => 1000]),
                'status' => 'completed',
                'cmd_id' => 'cmd-' . $i,
                'created_at' => $oldDate->copy()->addSeconds($i),
                'updated_at' => $oldDate->copy()->addSeconds($i),
                'sent_at' => $oldDate->copy()->addSeconds($i + 1),
                'ack_at' => $oldDate->copy()->addSeconds($i + 2),
            ]);
        }
        
        // Создаем новые команды, которые не должны быть заархивированы
        for ($i = 0; $i < 50; $i++) {
            DB::table('commands')->insert([
                'zone_id' => $zone->id,
                'node_id' => $node->id,
                'channel' => 'ph_pump',
                'cmd' => 'run_pump',
                'params' => json_encode(['duration_ms' => 1000]),
                'status' => 'completed',
                'cmd_id' => 'cmd-new-' . $i,
                'created_at' => Carbon::now()->subDays(5)->addSeconds($i),
                'updated_at' => Carbon::now()->subDays(5)->addSeconds($i),
            ]);
        }
        
        // Проверяем начальное количество
        $oldCount = Command::where('created_at', '<', Carbon::now()->subDays(90))->count();
        $this->assertEquals(1500, $oldCount);
        
        $totalCount = Command::count();
        $this->assertEquals(1550, $totalCount);
        
        // Запускаем команду архивирования
        $this->artisan('commands:archive', ['--days' => 90])
            ->assertSuccessful();
        
        // Проверяем, что старые команды заархивированы
        $archivedCount = CommandsArchive::count();
        $this->assertEquals(1500, $archivedCount);
        
        // Проверяем, что старые команды удалены из основной таблицы
        $remainingOld = Command::where('created_at', '<', Carbon::now()->subDays(90))->count();
        $this->assertEquals(0, $remainingOld);
        
        // Проверяем, что новые команды остались
        $remainingNew = Command::where('created_at', '>=', Carbon::now()->subDays(90))->count();
        $this->assertEquals(50, $remainingNew);
    }

    /**
     * Тест архивирования команд с pending статусом (не должны архивироваться).
     */
    public function test_archive_commands_skips_pending(): void
    {
        // Создаем необходимые зависимости
        $zone = \App\Models\Zone::factory()->create();
        $node = \App\Models\DeviceNode::factory()->create(['zone_id' => $zone->id]);
        
        $oldDate = Carbon::now()->subDays(95);
        
        // Создаем старые pending команды
        for ($i = 0; $i < 100; $i++) {
            DB::table('commands')->insert([
                'zone_id' => $zone->id,
                'node_id' => $node->id,
                'channel' => 'ph_pump',
                'cmd' => 'run_pump',
                'params' => json_encode(['duration_ms' => 1000]),
                'status' => Command::STATUS_QUEUED,
                'cmd_id' => 'cmd-pending-' . $i,
                'created_at' => $oldDate->copy()->addSeconds($i),
                'updated_at' => $oldDate->copy()->addSeconds($i),
            ]);
        }
        
        // Создаем старые completed команды
        for ($i = 0; $i < 100; $i++) {
            DB::table('commands')->insert([
                'zone_id' => $zone->id,
                'node_id' => $node->id,
                'channel' => 'ph_pump',
                'cmd' => 'run_pump',
                'params' => json_encode(['duration_ms' => 1000]),
                'status' => 'completed',
                'cmd_id' => 'cmd-completed-' . $i,
                'created_at' => $oldDate->copy()->addSeconds($i),
                'updated_at' => $oldDate->copy()->addSeconds($i),
                'ack_at' => $oldDate->copy()->addSeconds($i + 1),
            ]);
        }
        
        $this->artisan('commands:archive', ['--days' => 90])
            ->assertSuccessful();
        
        // Проверяем, что только completed команды заархивированы
        $archivedCount = CommandsArchive::count();
        $this->assertEquals(100, $archivedCount);
        
        // Проверяем, что pending команды остались
        $remainingPending = Command::where('status', Command::STATUS_QUEUED)->count();
        $this->assertEquals(100, $remainingPending);
    }

    /**
     * Тест обработки пустой таблицы команд.
     */
    public function test_archive_commands_empty_table(): void
    {
        $this->artisan('commands:archive', ['--days' => 90])
            ->assertSuccessful();
    }
}

