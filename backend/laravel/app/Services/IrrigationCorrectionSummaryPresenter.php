<?php

namespace App\Services;

use App\Support\Automation\RecipeNutritionRuntimeConfigResolver;
use App\Support\Automation\ZoneCorrectionResolvedConfigBuilder;
use Throwable;

/**
 * Сводка настроек коррекции для фазы irrigation (модалка полива, списки зон).
 */
final class IrrigationCorrectionSummaryPresenter
{
    public function __construct(
        private AutomationConfigDocumentService $documents,
        private ZoneCorrectionResolvedConfigBuilder $builder,
        private RecipeNutritionRuntimeConfigResolver $recipeNutritionRuntimeConfigResolver,
    ) {}

    /**
     * @param  array<string, mixed>|null  $irrigationTargets  срез effective targets['irrigation']
     * @param  array<string, mixed>|null  $nutritionTargets  срез effective targets['nutrition']
     * @return array<string, mixed>|null
     */
    public function summarize(int $zoneId, ?array $irrigationTargets, ?array $nutritionTargets = null): ?array
    {
        try {
            $corrPayload = $this->documents->getPayload(
                AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION,
                AutomationConfigRegistry::SCOPE_ZONE,
                $zoneId,
                false
            );
            $resolved = is_array($corrPayload['resolved_config'] ?? null) ? $corrPayload['resolved_config'] : [];
            $irrPhaseCfg = [];
            if (is_array($resolved['phases']['irrigation'] ?? null) && $resolved['phases']['irrigation'] !== []) {
                $irrPhaseCfg = $resolved['phases']['irrigation'];
            } else {
                $resolved = $this->builder->buildFromPayload($corrPayload);
            }
            $resolved = $this->recipeNutritionRuntimeConfigResolver->applyToResolvedConfig($resolved, $nutritionTargets);
            $irrPhaseCfg = is_array($resolved['phases']['irrigation'] ?? null)
                ? $resolved['phases']['irrigation']
                : [];
            $dosing = is_array($irrPhaseCfg['dosing'] ?? null) ? $irrPhaseCfg['dosing'] : [];
            $rawRatios = $irrPhaseCfg['ec_component_ratios'] ?? null;
            if (is_array($rawRatios)) {
                $ratios = $rawRatios;
            } elseif (is_object($rawRatios)) {
                $ratios = (array) $rawRatios;
            } else {
                $ratios = [];
            }
            $policy = is_array($irrPhaseCfg['ec_component_policy'] ?? null) ? $irrPhaseCfg['ec_component_policy'] : [];
            $policyIrrigation = is_array($policy['irrigation'] ?? null) ? $policy['irrigation'] : [];
            $excludedRaw = $irrPhaseCfg['ec_excluded_components'] ?? [];
            $excluded = [];
            if (is_array($excludedRaw)) {
                foreach ($excludedRaw as $x) {
                    if (is_string($x)) {
                        $s = strtolower(trim($x));
                        if ($s !== '') {
                            $excluded[] = $s;
                        }
                    } elseif (is_scalar($x)) {
                        $s = strtolower(trim((string) $x));
                        if ($s !== '') {
                            $excluded[] = $s;
                        }
                    }
                }
            }
            $irrigationTargets = $irrigationTargets ?? [];

            return [
                'ec_dosing_mode' => strtolower(trim((string) ($irrPhaseCfg['ec_dosing_mode'] ?? 'single'))) ?: 'single',
                'ec_excluded_components' => array_values(array_unique($excluded)),
                'ec_component_ratios' => $ratios,
                'ec_component_policy_irrigation' => $policyIrrigation,
                'dose_ec_channel' => isset($dosing['dose_ec_channel']) ? (string) $dosing['dose_ec_channel'] : null,
                'correction_during_irrigation' => array_key_exists('correction_during_irrigation', $irrigationTargets)
                    ? (bool) $irrigationTargets['correction_during_irrigation']
                    : null,
                'irrigation_ec_component' => (static function () use ($irrigationTargets): ?string {
                    $raw = $irrigationTargets['irrigation_ec_component'] ?? null;
                    if (! is_string($raw)) {
                        return null;
                    }
                    $normalized = strtolower(trim($raw));

                    return in_array($normalized, ['none', 'calcium', 'npk'], true) ? $normalized : null;
                })(),
            ];
        } catch (Throwable) {
            return null;
        }
    }
}
