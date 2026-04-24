<?php

namespace Tests\Feature;

use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;
use App\Models\ZoneEvent;
use App\Models\ZoneEventsArchive;
use Carbon\Carbon;

class ArchiveZoneEventsTest extends TestCase
{
    use RefreshDatabase;

    /**
     * Тест архивирования событий зон с chunking для предотвращения утечки памяти.
     */
    public function test_archive_zone_events_uses_chunking(): void
    {
        // Создаем необходимые зависимости
        $zone = \App\Models\Zone::factory()->create();
        
        // Создаем старые события для архивирования
        $oldDate = Carbon::now()->subDays(185);
        
        // Создаем 1200 старых событий (больше чем размер чанка 500)
        for ($i = 0; $i < 1200; $i++) {
            \Illuminate\Support\Facades\DB::table('zone_events')->insert([
                'zone_id' => $zone->id,
                'type' => 'INFO',
                'details' => json_encode(['message' => 'Test event ' . $i]),
                'created_at' => $oldDate->copy()->addSeconds($i),
            ]);
        }
        
        // Создаем новые события, которые не должны быть заархивированы
        for ($i = 0; $i < 50; $i++) {
            \Illuminate\Support\Facades\DB::table('zone_events')->insert([
                'zone_id' => $zone->id,
                'type' => 'INFO',
                'details' => json_encode(['message' => 'New event ' . $i]),
                'created_at' => Carbon::now()->subDays(5)->addSeconds($i),
            ]);
        }
        
        // Проверяем начальное количество
        $oldCount = ZoneEvent::where('created_at', '<', Carbon::now()->subDays(180))->count();
        $this->assertEquals(1200, $oldCount);
        
        $totalCount = ZoneEvent::count();
        $this->assertEquals(1250, $totalCount);
        
        // Запускаем команду архивирования
        $this->artisan('zone-events:archive', ['--days' => 180])
            ->assertSuccessful();
        
        // Проверяем, что старые события заархивированы
        $archivedCount = ZoneEventsArchive::count();
        $this->assertEquals(1200, $archivedCount);
        
        // Проверяем, что старые события удалены из основной таблицы
        $remainingOld = ZoneEvent::where('created_at', '<', Carbon::now()->subDays(180))->count();
        $this->assertEquals(0, $remainingOld);
        
        // Проверяем, что новые события остались
        $remainingNew = ZoneEvent::where('created_at', '>=', Carbon::now()->subDays(180))->count();
        $this->assertEquals(50, $remainingNew);
    }

    /**
     * Тест обработки пустой таблицы событий.
     */
    public function test_archive_zone_events_empty_table(): void
    {
        $this->artisan('zone-events:archive', ['--days' => 180])
            ->assertSuccessful();
    }

    /**
     * Тест обработки таблицы без старых событий.
     */
    public function test_archive_zone_events_no_old_records(): void
    {
        // Создаем необходимые зависимости
        $zone = \App\Models\Zone::factory()->create();
        
        // Создаем только новые события
        for ($i = 0; $i < 100; $i++) {
            \Illuminate\Support\Facades\DB::table('zone_events')->insert([
                'zone_id' => $zone->id,
                'type' => 'INFO',
                'details' => json_encode(['message' => 'New event ' . $i]),
                'created_at' => Carbon::now()->subDays(5)->addSeconds($i),
            ]);
        }
        
        $initialCount = ZoneEvent::count();
        $this->assertEquals(100, $initialCount);
        
        $this->artisan('zone-events:archive', ['--days' => 180])
            ->expectsOutput('Заархивировано событий: 0')
            ->assertSuccessful();
        
        $finalCount = ZoneEvent::count();
        $this->assertEquals(100, $finalCount);
    }
}

