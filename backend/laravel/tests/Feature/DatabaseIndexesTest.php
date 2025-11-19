<?php

namespace Tests\Feature;

use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\DB;
use Tests\TestCase;

class DatabaseIndexesTest extends TestCase
{
    use RefreshDatabase;

    /**
     * Проверка индексов для telemetry_samples
     */
    public function test_telemetry_samples_indexes_exist(): void
    {
        $indexes = DB::select("
            SELECT indexname 
            FROM pg_indexes 
            WHERE tablename = 'telemetry_samples' 
            AND indexname LIKE 'telemetry_samples_%'
            ORDER BY indexname
        ");

        $indexNames = array_column($indexes, 'indexname');
        
        $this->assertContains('telemetry_samples_zone_metric_ts_idx', $indexNames);
        $this->assertContains('telemetry_samples_node_ts_idx', $indexNames);
        $this->assertContains('telemetry_samples_metric_ts_idx', $indexNames);
        $this->assertContains('telemetry_samples_node_channel_ts_idx', $indexNames);
        $this->assertContains('telemetry_samples_created_at_idx', $indexNames);
    }

    /**
     * Проверка индексов для commands
     */
    public function test_commands_indexes_exist(): void
    {
        $indexes = DB::select("
            SELECT indexname 
            FROM pg_indexes 
            WHERE tablename = 'commands' 
            AND indexname LIKE 'commands_%'
            ORDER BY indexname
        ");

        $indexNames = array_column($indexes, 'indexname');
        
        $this->assertContains('commands_status_idx', $indexNames);
        $this->assertContains('commands_cmd_id_idx', $indexNames);
        $this->assertContains('commands_zone_status_idx', $indexNames);
        $this->assertContains('commands_node_status_idx', $indexNames);
        $this->assertContains('commands_created_at_idx', $indexNames);
        $this->assertContains('commands_sent_at_idx', $indexNames);
    }

    /**
     * Проверка индексов для alerts
     */
    public function test_alerts_indexes_exist(): void
    {
        $indexes = DB::select("
            SELECT indexname 
            FROM pg_indexes 
            WHERE tablename = 'alerts' 
            AND indexname LIKE 'alerts_%'
            ORDER BY indexname
        ");

        $indexNames = array_column($indexes, 'indexname');
        
        $this->assertContains('alerts_zone_status_idx', $indexNames);
        $this->assertContains('alerts_type_idx', $indexNames);
        $this->assertContains('alerts_source_code_idx', $indexNames);
        $this->assertContains('alerts_created_at_idx', $indexNames);
        $this->assertContains('alerts_resolved_at_idx', $indexNames);
        $this->assertContains('alerts_zone_type_status_idx', $indexNames);
    }

    /**
     * Проверка индексов для zone_events
     */
    public function test_zone_events_indexes_exist(): void
    {
        $indexes = DB::select("
            SELECT indexname 
            FROM pg_indexes 
            WHERE tablename = 'zone_events' 
            AND indexname LIKE 'zone_events_%'
            ORDER BY indexname
        ");

        $indexNames = array_column($indexes, 'indexname');
        
        $this->assertContains('zone_events_zone_id_created_at_idx', $indexNames);
        $this->assertContains('zone_events_type_idx', $indexNames);
        $this->assertContains('zone_events_zone_type_created_idx', $indexNames);
        $this->assertContains('zone_events_created_at_idx', $indexNames);
    }

    /**
     * Проверка использования индексов в запросах
     */
    public function test_indexes_are_used_in_queries(): void
    {
        // Создаем тестовые данные
        $zone = \App\Models\Zone::factory()->create();
        $node = \App\Models\DeviceNode::factory()->create(['zone_id' => $zone->id]);
        
        \App\Models\TelemetrySample::factory()->create([
            'zone_id' => $zone->id,
            'node_id' => $node->id,
            'metric_type' => 'PH',
            'ts' => now(),
        ]);

        // Проверяем, что запрос использует индекс
        $explain = DB::select("
            EXPLAIN (FORMAT JSON)
            SELECT * FROM telemetry_samples 
            WHERE zone_id = ? AND metric_type = ? AND ts >= ?
        ", [$zone->id, 'PH', now()->subDay()]);

        // EXPLAIN возвращает массив с одним элементом
        $result = is_array($explain) ? $explain[0] : $explain;
        $planData = is_string($result->explain ?? null) 
            ? json_decode($result->explain, true) 
            : (is_array($result) ? $result : []);
        
        if (empty($planData)) {
            $this->markTestSkipped('Could not parse EXPLAIN result');
            return;
        }

        $plan = is_array($planData) && isset($planData[0]) ? $planData[0] : $planData;
        $this->assertNotNull($plan);
        
        // Проверяем, что используется индекс (Index Scan или Index Only Scan)
        $nodeType = $plan['Plan']['Node Type'] ?? '';
        $this->assertTrue(
            str_contains($nodeType, 'Index') ||
            $this->hasIndexScan($plan['Plan'] ?? []),
            "Query should use index, but got: {$nodeType}"
        );
    }

    /**
     * Рекурсивная проверка использования индекса в плане запроса
     */
    private function hasIndexScan(array $plan): bool
    {
        if (isset($plan['Node Type']) && str_contains($plan['Node Type'], 'Index')) {
            return true;
        }

        if (isset($plan['Plans'])) {
            foreach ($plan['Plans'] as $subPlan) {
                if ($this->hasIndexScan($subPlan)) {
                    return true;
                }
            }
        }

        return false;
    }
}

