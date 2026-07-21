<?php

namespace Tests\Unit\Services\LaunchFlow;

use App\Models\Zone;
use App\Services\LaunchFlow\LaunchFlowReadinessEnricher;
use App\Services\ZoneReadinessService;
use Illuminate\Support\Facades\Route;
use Mockery;
use Tests\TestCase;

class LaunchFlowReadinessEnricherTest extends TestCase
{
    protected function tearDown(): void
    {
        Mockery::close();
        parent::tearDown();
    }

    public function test_missing_binding_action_points_to_zones_show_devices_tab(): void
    {
        $zone = new Zone;
        $zone->id = 42;

        $readiness = Mockery::mock(ZoneReadinessService::class);
        $readiness->shouldReceive('validate')
            ->once()
            ->with(42)
            ->andReturn([
                'ready' => false,
                'warnings' => [],
                'details' => [
                    'checks' => [
                        'has_nodes' => true,
                        'online_nodes' => true,
                    ],
                    'error_details' => [
                        [
                            'type' => 'missing_bindings',
                            'bindings' => ['pump_main'],
                        ],
                    ],
                ],
            ]);

        $enricher = new LaunchFlowReadinessEnricher($readiness);
        $result = $enricher->forZone($zone);

        $this->assertFalse($result['ready']);
        $this->assertCount(1, $result['blockers']);
        $this->assertSame('missing_binding:pump_main', $result['blockers'][0]['code']);
        $this->assertSame('zones.show', $result['blockers'][0]['action']['route']['name']);
        $this->assertSame(
            ['zoneId' => 42, 'tab' => 'devices'],
            $result['blockers'][0]['action']['route']['params']
        );
        $this->assertTrue(Route::has($result['blockers'][0]['action']['route']['name']));
    }

    public function test_missing_calibration_action_points_to_zones_show_automation_tab(): void
    {
        $zone = new Zone;
        $zone->id = 7;

        $readiness = Mockery::mock(ZoneReadinessService::class);
        $readiness->shouldReceive('validate')
            ->once()
            ->with(7)
            ->andReturn([
                'ready' => false,
                'warnings' => [],
                'details' => [
                    'checks' => [
                        'has_nodes' => true,
                        'online_nodes' => true,
                    ],
                    'error_details' => [
                        [
                            'type' => 'missing_calibrations',
                            'bindings' => ['pump_acid'],
                        ],
                    ],
                ],
            ]);

        $enricher = new LaunchFlowReadinessEnricher($readiness);
        $result = $enricher->forZone($zone);

        $this->assertSame('missing_calibration:pump_acid', $result['blockers'][0]['code']);
        $this->assertSame('zones.show', $result['blockers'][0]['action']['route']['name']);
        $this->assertSame(
            ['zoneId' => 7, 'tab' => 'automation'],
            $result['blockers'][0]['action']['route']['params']
        );
        $this->assertTrue(Route::has($result['blockers'][0]['action']['route']['name']));
    }

    public function test_no_nodes_error_detail_is_not_duplicated_as_separate_blocker(): void
    {
        $zone = new Zone;
        $zone->id = 9;

        $readiness = Mockery::mock(ZoneReadinessService::class);
        $readiness->shouldReceive('validate')
            ->once()
            ->with(9)
            ->andReturn([
                'ready' => false,
                'warnings' => [],
                'details' => [
                    'checks' => [
                        'has_nodes' => false,
                        'online_nodes' => false,
                    ],
                    'error_details' => [
                        [
                            'type' => 'no_nodes',
                            'message' => 'Zone has no bound nodes',
                        ],
                        [
                            'type' => 'no_online_nodes',
                            'message' => 'Zone has no online nodes',
                        ],
                    ],
                ],
            ]);

        $enricher = new LaunchFlowReadinessEnricher($readiness);
        $result = $enricher->forZone($zone);

        $codes = array_column($result['blockers'], 'code');
        $this->assertSame(['no_nodes_bound', 'nodes_offline'], $codes);
    }
}
