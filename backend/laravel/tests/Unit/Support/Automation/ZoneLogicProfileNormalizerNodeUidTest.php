<?php

namespace Tests\Unit\Support\Automation;

use App\Support\Automation\ZoneLogicProfileNormalizer;
use Tests\TestCase;

class ZoneLogicProfileNormalizerNodeUidTest extends TestCase
{
    public function test_two_tank_steps_keep_node_uid(): void
    {
        $normalizer = new ZoneLogicProfileNormalizer();
        $plans = $normalizer->buildCommandPlans([
            'diagnostics' => [
                'execution' => [
                    'topology' => 'two_tank',
                    'two_tank_commands' => [
                        'irrigation_start' => [
                            [
                                'node_uid' => 'nd-test-irrig-1',
                                'channel' => 'valve_solution_supply',
                                'cmd' => 'set_relay',
                                'params' => ['state' => true],
                            ],
                            [
                                'node_uid' => 'nd-test-irrig-1',
                                'channel' => 'valve_irrigation',
                                'cmd' => 'set_relay',
                                'params' => ['state' => true],
                            ],
                            [
                                'node_uid' => 'nd-test-irrig-1',
                                'channel' => 'pump_main',
                                'cmd' => 'run_pump',
                                'params' => ['duration_ms' => 2000],
                            ],
                        ],
                    ],
                ],
            ],
        ]);

        $steps = $plans['plans']['diagnostics']['steps'];
        $this->assertSame('nd-test-irrig-1', $steps[0]['node_uid']);
        $this->assertSame('valve_solution_supply', $steps[0]['channel']);
        $this->assertSame('nd-test-irrig-1', $steps[2]['node_uid']);
        $this->assertSame('pump_main', $steps[2]['channel']);
        $this->assertSame('nd-test-irrig-1', $plans['plans']['irrigation_start'][0]['node_uid']);
        $this->assertSame('pump_main', $plans['plans']['irrigation_start'][2]['channel']);
    }
}
