<?php

namespace App\Support\Automation;

use App\Services\ZoneCorrectionConfigCatalog;

final class RecipeNutritionRuntimeConfigResolver
{
    private const EC_COMPONENT_ORDER = ['calcium', 'magnesium', 'npk', 'micro'];

    /**
     * @param  array<string, mixed>  $resolvedConfig
     * @param  array<string, mixed>|null  $nutrition
     * @return array<string, mixed>
     */
    public function applyToResolvedConfig(array $resolvedConfig, ?array $nutrition): array
    {
        if ($resolvedConfig === [] || array_is_list($resolvedConfig)) {
            return $resolvedConfig;
        }

        if (! is_array($nutrition) || array_is_list($nutrition)) {
            return $resolvedConfig;
        }

        $mode = strtolower(trim((string) ($nutrition['mode'] ?? '')));
        if ($mode === '') {
            return $resolvedConfig;
        }

        $resolved = $resolvedConfig;
        $solutionVolume = $this->toPositiveFloat($nutrition['solution_volume_l'] ?? null);
        if ($solutionVolume !== null) {
            data_set($resolved, 'base.dosing.solution_volume_l', $solutionVolume);
            foreach (ZoneCorrectionConfigCatalog::PHASES as $phase) {
                data_set($resolved, "phases.{$phase}.dosing.solution_volume_l", $solutionVolume);
            }
        }

        $componentRatios = $this->extractComponentRatios($nutrition['components'] ?? null);
        if (in_array($mode, ['ratio_ec_pid', 'delta_ec_by_k'], true) && $componentRatios !== []) {
            $this->applySolutionFillCalciumOnly($resolved, $componentRatios);
            $this->applyTankRecircSequentialPipeline($resolved, $componentRatios, $nutrition);
            $this->applyIrrigationEcExcluded($resolved, $componentRatios);
        }

        $meta = data_get($resolved, 'meta');
        $meta = is_array($meta) && ! array_is_list($meta) ? $meta : [];
        $meta['recipe_nutrient_mode'] = $mode;
        if ($componentRatios !== []) {
            $meta['recipe_component_ratios'] = $componentRatios;
        }

        $irrigationSystemType = strtolower(trim((string) ($nutrition['irrigation_system_type'] ?? '')));
        if ($irrigationSystemType !== '') {
            $meta['recipe_irrigation_system_type'] = $irrigationSystemType;
            data_set($resolved, 'phases.irrigation.system_type', $irrigationSystemType);
        }
        $substrateType = strtolower(trim((string) ($nutrition['substrate_type'] ?? '')));
        if ($substrateType !== '') {
            $meta['recipe_substrate_type'] = $substrateType;
            data_set($resolved, 'phases.irrigation.substrate_type', $substrateType);
        }

        data_set($resolved, 'meta', $meta);

        return $resolved;
    }

    /**
     * solution_fill: only calcium dosing (no full multi / no pH from nutrition policy).
     *
     * @param  array<string, mixed>  $resolved
     * @param  array<string, float>  $componentRatios
     */
    private function applySolutionFillCalciumOnly(array &$resolved, array $componentRatios): void
    {
        $calciumRatio = $componentRatios['calcium'] ?? null;
        if ($calciumRatio === null) {
            return;
        }

        data_set($resolved, 'phases.solution_fill.ec_dosing_mode', 'single');
        data_set($resolved, 'phases.solution_fill.ec_component_ratios', ['calcium' => $calciumRatio]);
        data_set(
            $resolved,
            'phases.solution_fill.ec_excluded_components',
            $this->mergeExcludedComponents(
                data_get($resolved, 'phases.solution_fill.ec_excluded_components'),
                array_values(array_filter(
                    array_keys($componentRatios),
                    static fn (string $component): bool => $component !== 'calcium'
                ))
            )
        );

        $policy = data_get($resolved, 'phases.solution_fill.ec_component_policy');
        $policy = is_array($policy) && ! array_is_list($policy) ? $policy : [];
        $policy['solution_fill'] = ['calcium' => $calciumRatio];
        $policy['active_component'] = 'calcium';
        data_set($resolved, 'phases.solution_fill.ec_component_policy', $policy);
    }

    /**
     * tank_recirc: sequential pipeline ratios (Ca→Mg→NPK→Micro), not irrigation exclude-npk model.
     *
     * @param  array<string, mixed>  $resolved
     * @param  array<string, float>  $componentRatios
     * @param  array<string, mixed>  $nutrition
     */
    private function applyTankRecircSequentialPipeline(array &$resolved, array $componentRatios, array $nutrition): void
    {
        $recipeEcDosingMode = strtolower(trim((string) ($nutrition['ec_dosing_mode'] ?? '')));
        $recircEcDosingMode = $recipeEcDosingMode === 'parallel' ? 'multi_parallel' : 'multi_sequential';

        data_set($resolved, 'phases.tank_recirc.ec_dosing_mode', $recircEcDosingMode);
        data_set($resolved, 'phases.tank_recirc.ec_component_ratios', $componentRatios);
        data_set($resolved, 'phases.tank_recirc.ec_excluded_components', []);

        $pipelineRatios = [];
        foreach (self::EC_COMPONENT_ORDER as $component) {
            if (($componentRatios[$component] ?? 0.0) > 0) {
                $pipelineRatios[$component] = $componentRatios[$component];
            }
        }
        foreach ($componentRatios as $component => $ratio) {
            if (! array_key_exists($component, $pipelineRatios) && $ratio > 0) {
                $pipelineRatios[$component] = $ratio;
            }
        }

        $policy = data_get($resolved, 'phases.tank_recirc.ec_component_policy');
        $policy = is_array($policy) && ! array_is_list($policy) ? $policy : [];
        unset($policy['irrigation']);
        $policy['tank_recirc'] = $pipelineRatios;
        $policy['pipeline'] = array_keys($pipelineRatios);
        data_set($resolved, 'phases.tank_recirc.ec_component_policy', $policy);
    }

    /**
     * irrigation: no EC dosing — all recipe EC components excluded.
     *
     * @param  array<string, mixed>  $resolved
     * @param  array<string, float>  $componentRatios
     */
    private function applyIrrigationEcExcluded(array &$resolved, array $componentRatios): void
    {
        data_set($resolved, 'phases.irrigation.ec_component_ratios', []);
        data_set(
            $resolved,
            'phases.irrigation.ec_excluded_components',
            $this->mergeExcludedComponents(
                data_get($resolved, 'phases.irrigation.ec_excluded_components'),
                array_keys($componentRatios)
            )
        );
        data_set($resolved, 'phases.irrigation.ec_dosing_mode', 'single');

        $policy = data_get($resolved, 'phases.irrigation.ec_component_policy');
        $policy = is_array($policy) && ! array_is_list($policy) ? $policy : [];
        unset($policy['irrigation']);
        $policy['irrigation'] = [];
        $policy['needs_ec'] = false;
        data_set($resolved, 'phases.irrigation.ec_component_policy', $policy);
    }

    /**
     * @return array<string, float>
     */
    private function extractComponentRatios(mixed $rawComponents): array
    {
        if (! is_array($rawComponents) || array_is_list($rawComponents)) {
            return [];
        }

        $ratios = [];
        foreach ($rawComponents as $name => $componentConfig) {
            if (! is_string($name) || ! is_array($componentConfig) || array_is_list($componentConfig)) {
                continue;
            }

            $normalizedName = strtolower(trim($name));
            if ($normalizedName === '') {
                continue;
            }

            $ratio = $this->toPositiveFloat($componentConfig['ratio_pct'] ?? null);
            if ($ratio === null) {
                continue;
            }

            $ratios[$normalizedName] = round($ratio, 4);
        }

        return $ratios;
    }

    /**
     * @param  array<int, string>  $extra
     * @return array<int, string>
     */
    private function mergeExcludedComponents(mixed $current, array $extra): array
    {
        $items = [];
        if (is_array($current)) {
            foreach ($current as $component) {
                $normalized = strtolower(trim((string) $component));
                if ($normalized !== '') {
                    $items[] = $normalized;
                }
            }
        }

        foreach ($extra as $component) {
            $normalized = strtolower(trim((string) $component));
            if ($normalized !== '') {
                $items[] = $normalized;
            }
        }

        return array_values(array_unique($items));
    }

    private function toPositiveFloat(mixed $value): ?float
    {
        if ($value === null || $value === '') {
            return null;
        }

        try {
            $normalized = (float) $value;
        } catch (\Throwable) {
            return null;
        }

        return $normalized > 0 ? $normalized : null;
    }
}
