<?php

namespace App\Support\Automation;

class ZoneLogicProfileNormalizer
{
    /**
     * @param  array<string, mixed>  $profile
     * @return array<string, mixed>
     */
    public function normalizeProfile(string $mode, array $profile, string $commandPlanSource = 'automation_logic_profile_normalized'): array
    {
        $subsystems = $this->normalizeSubsystems(
            is_array($profile['subsystems'] ?? null) && ! array_is_list($profile['subsystems'])
                ? $profile['subsystems']
                : []
        );

        return array_merge($profile, [
            'mode' => $mode,
            'subsystems' => $subsystems,
            'command_plans' => $this->buildCommandPlans($subsystems, $commandPlanSource),
        ]);
    }

    /**
     * @param  array<string, mixed>  $subsystems
     * @return array<string, mixed>
     */
    public function normalizeSubsystems(array $subsystems): array
    {
        $normalized = [];

        foreach ($subsystems as $name => $subsystem) {
            if (! is_string($name) || ! is_array($subsystem) || array_is_list($subsystem)) {
                continue;
            }

            $entry = [];
            if (array_key_exists('enabled', $subsystem)) {
                $entry['enabled'] = (bool) $subsystem['enabled'];
            }

            $execution = [];
            if (isset($subsystem['execution']) && is_array($subsystem['execution'])) {
                $execution = $subsystem['execution'];
                if ($name === 'diagnostics') {
                    $execution = $this->normalizeDiagnosticsExecution($execution);
                }
            }

            if ($execution !== []) {
                $entry['execution'] = $execution;
            }

            if ($entry !== []) {
                $normalized[$name] = $entry;
            }
        }

        return $normalized;
    }

    /**
     * @param  array<string, mixed>  $subsystems
     * @return array<string, mixed>
     */
    public function buildCommandPlans(array $subsystems, string $source = 'automation_logic_profile_upsert'): array
    {
        $execution = data_get($subsystems, 'diagnostics.execution');
        $execution = is_array($execution) && ! array_is_list($execution) ? $execution : [];

        $twoTankCommands = data_get($execution, 'two_tank_commands');
        $twoTankCommands = is_array($twoTankCommands) && ! array_is_list($twoTankCommands) ? $twoTankCommands : [];

        $steps = $this->resolveCommandPlanSteps($execution, $twoTankCommands);

        return [
            'schema_version' => 1,
            'plan_version' => 1,
            'source' => $source,
            'plans' => [
                'diagnostics' => [
                    'execution' => $execution,
                    'two_tank_commands' => $twoTankCommands,
                    'steps' => $steps,
                ],
            ],
        ];
    }

    /**
     * @param  array<string, mixed>  $execution
     * @return array<string, mixed>
     */
    private function normalizeDiagnosticsExecution(array $execution): array
    {
        $workflow = $execution['workflow'] ?? null;
        if (is_string($workflow) && strtolower(trim($workflow)) === 'startup') {
            $execution['workflow'] = 'cycle_start';
        }

        return $execution;
    }

    /**
     * @param  array<string, mixed>  $execution
     * @param  array<string, mixed>  $twoTankCommands
     * @return array<int, array<string, mixed>>
     */
    private function resolveCommandPlanSteps(array $execution, array $twoTankCommands): array
    {
        $fromTwoTankSteps = data_get($twoTankCommands, 'steps');
        if (is_array($fromTwoTankSteps) && $fromTwoTankSteps !== []) {
            $normalized = $this->normalizeCommandPlanSteps($fromTwoTankSteps);
            if ($normalized !== []) {
                return $normalized;
            }
        }

        $rawExecutionSteps = data_get($execution, 'steps');
        if (is_array($rawExecutionSteps) && $rawExecutionSteps !== []) {
            $normalized = $this->normalizeCommandPlanSteps($rawExecutionSteps);
            if ($normalized !== []) {
                return $normalized;
            }
        }

        return $this->buildFallbackStepsFromTwoTankCommands($twoTankCommands);
    }

    /**
     * @param  array<int, mixed>  $rawSteps
     * @return array<int, array<string, mixed>>
     */
    private function normalizeCommandPlanSteps(array $rawSteps): array
    {
        $steps = [];

        foreach ($rawSteps as $index => $rawStep) {
            if (! is_array($rawStep) || array_is_list($rawStep)) {
                continue;
            }

            $channel = trim((string) ($rawStep['channel'] ?? ''));
            $cmd = trim((string) ($rawStep['cmd'] ?? ''));
            $params = $rawStep['params'] ?? [];
            if ($channel === '' || $cmd === '' || ! is_array($params)) {
                continue;
            }

            $steps[] = [
                'name' => isset($rawStep['name']) ? (string) $rawStep['name'] : 'step_'.((int) $index + 1),
                'channel' => $channel,
                'cmd' => $cmd,
                'params' => $params,
                'timeout_sec' => isset($rawStep['timeout_sec']) ? (int) $rawStep['timeout_sec'] : null,
                'allow_no_effect' => (bool) ($rawStep['allow_no_effect'] ?? false),
                'dedupe_bypass' => (bool) ($rawStep['dedupe_bypass'] ?? false),
            ];
        }

        return $steps;
    }

    /**
     * @param  array<string, mixed>  $twoTankCommands
     * @return array<int, array<string, mixed>>
     */
    private function buildFallbackStepsFromTwoTankCommands(array $twoTankCommands): array
    {
        $steps = [];

        foreach ($twoTankCommands as $planName => $planCommands) {
            if (! is_string($planName) || ! is_array($planCommands) || ! array_is_list($planCommands)) {
                continue;
            }

            foreach ($planCommands as $position => $rawStep) {
                if (! is_array($rawStep) || array_is_list($rawStep)) {
                    continue;
                }

                $channel = trim((string) ($rawStep['channel'] ?? ''));
                $cmd = trim((string) ($rawStep['cmd'] ?? ''));
                $params = $rawStep['params'] ?? [];
                if ($channel === '' || $cmd === '' || ! is_array($params)) {
                    continue;
                }

                $steps[] = [
                    'name' => $planName.'_'.((int) $position + 1),
                    'channel' => $channel,
                    'cmd' => $cmd,
                    'params' => $params,
                    'allow_no_effect' => (bool) ($rawStep['allow_no_effect'] ?? false),
                    'dedupe_bypass' => (bool) ($rawStep['dedupe_bypass'] ?? false),
                ];
            }
        }

        return $steps;
    }
}
