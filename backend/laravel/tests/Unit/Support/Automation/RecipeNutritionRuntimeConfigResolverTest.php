<?php

namespace Tests\Unit\Support\Automation;

use App\Services\ZoneCorrectionConfigCatalog;
use App\Support\Automation\RecipeNutritionRuntimeConfigResolver;
use Tests\TestCase;

class RecipeNutritionRuntimeConfigResolverTest extends TestCase
{
    public function test_phase_policies_are_calcium_fill_sequential_recirc_and_irrigation_ec_excluded(): void
    {
        $resolver = new RecipeNutritionRuntimeConfigResolver();

        $resolved = $resolver->applyToResolvedConfig(
            [
                'base' => ZoneCorrectionConfigCatalog::defaults(),
                'phases' => [
                    'solution_fill' => ZoneCorrectionConfigCatalog::defaults(),
                    'tank_recirc' => ZoneCorrectionConfigCatalog::defaults(),
                    'irrigation' => ZoneCorrectionConfigCatalog::defaults(),
                ],
                'meta' => [],
            ],
            [
                'mode' => 'ratio_ec_pid',
                'ec_dosing_mode' => 'sequential',
                'solution_volume_l' => 120.0,
                'components' => [
                    'npk' => ['ratio_pct' => 40.0],
                    'calcium' => ['ratio_pct' => 30.0],
                    'magnesium' => ['ratio_pct' => 20.0],
                    'micro' => ['ratio_pct' => 10.0],
                ],
            ]
        );

        $this->assertSame(120.0, data_get($resolved, 'base.dosing.solution_volume_l'));
        $this->assertSame(['calcium' => 30.0], data_get($resolved, 'phases.solution_fill.ec_component_ratios'));
        $this->assertSame('single', data_get($resolved, 'phases.solution_fill.ec_dosing_mode'));
        $this->assertSame('calcium', data_get($resolved, 'phases.solution_fill.ec_component_policy.active_component'));
        $this->assertContains('npk', data_get($resolved, 'phases.solution_fill.ec_excluded_components'));
        $this->assertContains('magnesium', data_get($resolved, 'phases.solution_fill.ec_excluded_components'));
        $this->assertContains('micro', data_get($resolved, 'phases.solution_fill.ec_excluded_components'));

        $this->assertSame('multi_sequential', data_get($resolved, 'phases.tank_recirc.ec_dosing_mode'));
        $this->assertSame(
            [
                'npk' => 40.0,
                'calcium' => 30.0,
                'magnesium' => 20.0,
                'micro' => 10.0,
            ],
            data_get($resolved, 'phases.tank_recirc.ec_component_ratios')
        );
        $this->assertSame([], data_get($resolved, 'phases.tank_recirc.ec_excluded_components'));
        $this->assertSame(
            ['calcium', 'magnesium', 'npk', 'micro'],
            data_get($resolved, 'phases.tank_recirc.ec_component_policy.pipeline')
        );

        $this->assertSame([], data_get($resolved, 'phases.irrigation.ec_component_ratios'));
        $this->assertFalse(data_get($resolved, 'phases.irrigation.ec_component_policy.needs_ec'));
        $excluded = data_get($resolved, 'phases.irrigation.ec_excluded_components');
        $this->assertContains('npk', $excluded);
        $this->assertContains('calcium', $excluded);
        $this->assertContains('magnesium', $excluded);
        $this->assertContains('micro', $excluded);
    }
}
