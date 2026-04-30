<?php

namespace App\Services;

class AlertPolicyService
{
    public const MODE_MANUAL_ACK = 'manual_ack';

    public const MODE_AUTO_RESOLVE_ON_RECOVERY = 'auto_resolve_on_recovery';

    public const MODES = [
        self::MODE_MANUAL_ACK,
        self::MODE_AUTO_RESOLVE_ON_RECOVERY,
    ];

    private const POLICY_MANAGED_CODES = [
        'biz_ae3_task_failed',
        'biz_prepare_recirculation_retry_exhausted',
        'biz_correction_exhausted',
        'biz_ph_correction_no_effect',
        'biz_ec_correction_no_effect',
        'biz_zone_correction_config_missing',
        'biz_zone_dosing_calibration_missing',
        'biz_zone_pid_config_missing',
        'biz_zone_recipe_phase_targets_missing',
    ];

    private const AUTO_RESOLVE_ELIGIBLE_CODES = [
        'biz_zone_correction_config_missing',
        'biz_zone_dosing_calibration_missing',
        'biz_zone_pid_config_missing',
        'biz_zone_recipe_phase_targets_missing',
    ];

    public function __construct(
        private readonly AutomationConfigDocumentService $documents,
    ) {}

    public function currentMode(): string
    {
        $payload = $this->documents->getPayload(
            AutomationConfigRegistry::NAMESPACE_SYSTEM_ALERT_POLICIES,
            AutomationConfigRegistry::SCOPE_SYSTEM,
            0,
        );
        $mode = is_string($payload['ae3_operational_resolution_mode'] ?? null)
            ? trim($payload['ae3_operational_resolution_mode'])
            : '';

        return in_array($mode, self::MODES, true)
            ? $mode
            : self::MODE_MANUAL_ACK;
    }

    /**
     * @return array<string, mixed>
     */
    public function documentPayload(): array
    {
        return [
            'ae3_operational_resolution_mode' => $this->currentMode(),
        ];
    }

    /**
     * @return list<string>
     */
    public function autoResolveEligibleCodes(): array
    {
        return self::AUTO_RESOLVE_ELIGIBLE_CODES;
    }

    /**
     * Список alert-кодов, которые в режиме `manual_ack` означают,
     * что AE3 не возобновит автоматику без ручного вмешательства.
     * Используется backend/UI для индикации «автоматика заблокирована ошибкой».
     *
     * @return list<string>
     */
    public function policyManagedCodes(): array
    {
        return self::POLICY_MANAGED_CODES;
    }

    public function isPolicyManagedCode(?string $code): bool
    {
        $normalized = $this->normalizeCode($code);

        return $normalized !== '' && in_array($normalized, self::POLICY_MANAGED_CODES, true);
    }

    public function allowsAutoResolve(?string $code): bool
    {
        $normalized = $this->normalizeCode($code);
        if ($normalized === '') {
            return false;
        }

        return $this->currentMode() === self::MODE_AUTO_RESOLVE_ON_RECOVERY
            && in_array($normalized, self::AUTO_RESOLVE_ELIGIBLE_CODES, true);
    }

    /**
     * @param  array<string, mixed>  $context
     */
    public function blocksAutomaticResolution(?string $code, array $context = []): bool
    {
        $normalized = $this->normalizeCode($code);
        if (! $this->isPolicyManagedCode($normalized)) {
            return false;
        }

        $resolvedVia = strtolower(trim((string) ($context['resolved_via'] ?? 'auto')));
        if ($resolvedVia === 'manual') {
            return false;
        }

        return ! $this->allowsAutoResolve($normalized);
    }

    private function normalizeCode(?string $code): string
    {
        return strtolower(trim((string) $code));
    }
}
