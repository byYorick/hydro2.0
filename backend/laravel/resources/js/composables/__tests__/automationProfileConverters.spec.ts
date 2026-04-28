import { describe, expect, it } from 'vitest';
import {
    assignmentsToApplyPayload,
    bindingsResponseToAssignments,
    profileToZoneLogicProfile,
    zoneLogicProfileToProfile,
} from '../automationProfileConverters';
import { automationProfileDefaults } from '@/schemas/automationProfile';

function collectUndefinedPaths(value: unknown, path = ''): string[] {
    if (value === undefined) return [path];
    if (!value || typeof value !== 'object') return [];
    return Object.entries(value as Record<string, unknown>).flatMap(([key, nested]) =>
        collectUndefinedPaths(nested, path ? `${path}.${key}` : key),
    );
}

describe('zoneLogicProfileToProfile', () => {
    it('falls back to defaults on empty payload', () => {
        const profile = zoneLogicProfileToProfile(null);
        expect(profile.waterForm.systemType).toBe('drip');
        expect(profile.lightingForm.enabled).toBe(false);
        expect(profile.zoneClimateForm.enabled).toBe(false);
    });

    it('reads water.system_type and targets', () => {
        const profile = zoneLogicProfileToProfile({
            water: {
                system_type: 'nft',
                correction: { target_ph: 5.8, target_ec: 1.4 },
                irrigation: { interval_minutes: 15, duration_seconds: 60 },
            },
        });
        expect(profile.waterForm.systemType).toBe('nft');
        expect(profile.waterForm.targetPh).toBe(5.8);
        expect(profile.waterForm.targetEc).toBe(1.4);
        expect(profile.waterForm.intervalMinutes).toBe(15);
        expect(profile.waterForm.durationSeconds).toBe(60);
    });

    it('reads lighting block', () => {
        const profile = zoneLogicProfileToProfile({
            lighting: { enabled: true, lux_day: 50000, hours_on: 14, schedule_start: '05:00' },
        });
        expect(profile.lightingForm.enabled).toBe(true);
        expect(profile.lightingForm.luxDay).toBe(50000);
        expect(profile.lightingForm.hoursOn).toBe(14);
        expect(profile.lightingForm.scheduleStart).toBe('05:00');
    });

    it('reads zone_climate.enabled', () => {
        const profile = zoneLogicProfileToProfile({ zone_climate: { enabled: true } });
        expect(profile.zoneClimateForm.enabled).toBe(true);
    });

    it('reads canonical active zone.logic_profile subsystems', () => {
        const profile = zoneLogicProfileToProfile({
            active_mode: 'working',
            profiles: {
                working: {
                    mode: 'working',
                    is_active: true,
                    subsystems: {
                        irrigation: {
                            enabled: true,
                            execution: {
                                system_type: 'substrate_trays',
                                tanks_count: 3,
                                interval_sec: 900,
                                duration_sec: 45,
                                clean_tank_fill_l: 210,
                                nutrient_tank_target_l: 180,
                                irrigation_batch_l: 12,
                                fill_temperature_c: 21,
                                schedule: [{ start: '05:30', end: '06:45' }],
                                drain_control: { enabled: true, target_percent: 18 },
                            },
                            decision: {
                                strategy: 'smart_soil_v1',
                                config: {
                                    lookback_sec: 1200,
                                    min_samples: 4,
                                    stale_after_sec: 600,
                                    hysteresis_pct: 3,
                                    spread_alert_threshold_pct: 15,
                                },
                            },
                            recovery: {
                                max_continue_attempts: 6,
                                timeout_sec: 700,
                                auto_replay_after_setup: true,
                                max_setup_replays: 2,
                            },
                            safety: { stop_on_solution_min: true },
                        },
                        lighting: {
                            enabled: true,
                            execution: {
                                interval_sec: 1800,
                                lux: { day: 42000, night: 1000 },
                                photoperiod: { hours_on: 16 },
                                schedule: [{ start: '04:00', end: '20:00' }],
                            },
                        },
                        zone_climate: { enabled: true, execution: {} },
                        diagnostics: {
                            enabled: true,
                            execution: {
                                interval_sec: 600,
                                workflow: 'cycle_start',
                                clean_tank_full_threshold: 0.9,
                                refill: { duration_sec: 40, timeout_sec: 500, channel: 'fill_valve' },
                                required_node_types: ['irrig', 'level'],
                                correction: {
                                    max_ec_correction_attempts: 7,
                                    max_ph_correction_attempts: 8,
                                    prepare_recirculation_max_attempts: 3,
                                    prepare_recirculation_max_correction_attempts: 12,
                                    stabilization_sec: 55,
                                },
                                fail_safe_guards: {
                                    clean_fill_min_check_delay_ms: 1000,
                                    irrigation_stop_on_solution_min: true,
                                },
                            },
                        },
                        solution_change: {
                            enabled: true,
                            execution: { interval_sec: 7200, duration_sec: 180 },
                        },
                    },
                    updated_at: null,
                },
            },
        });

        expect(profile.waterForm.systemType).toBe('substrate_trays');
        expect(profile.waterForm.tanksCount).toBe(3);
        expect(profile.waterForm.intervalMinutes).toBe(15);
        expect(profile.waterForm.durationSeconds).toBe(45);
        expect(profile.waterForm.fillWindowStart).toBe('05:30');
        expect(profile.waterForm.enableDrainControl).toBe(true);
        expect(profile.waterForm.diagnosticsIntervalMinutes).toBe(10);
        expect(profile.waterForm.refillRequiredNodeTypes).toBe('irrig,level');
        expect(profile.waterForm.solutionChangeIntervalMinutes).toBe(120);
        expect(profile.lightingForm.enabled).toBe(true);
        expect(profile.lightingForm.luxDay).toBe(42000);
        expect(profile.lightingForm.intervalMinutes).toBe(30);
        expect(profile.zoneClimateForm.enabled).toBe(true);
    });

    it('accepts plain number strings', () => {
        const profile = zoneLogicProfileToProfile({
            water: {
                clean_tank_fill_l: '200',
                nutrient_tank_target_l: '180',
                clean_tank_full_threshold: '95',
            },
        });
        expect(profile.waterForm.cleanTankFillL).toBe(200);
        expect(profile.waterForm.nutrientTankTargetL).toBe(180);
        expect(profile.waterForm.cleanTankFullThreshold).toBe(0.95);
    });
});

describe('profileToZoneLogicProfile', () => {
    it('emits canonical active profile with subsystems', () => {
        const payload = profileToZoneLogicProfile(automationProfileDefaults);
        expect(payload).not.toHaveProperty('payload');
        expect(payload).not.toHaveProperty('water');
        expect(payload.active_mode).toBe('working');
        expect(payload.profiles).toHaveProperty('working');

        const working = (payload.profiles as Record<string, unknown>).working as {
            mode?: string;
            is_active?: boolean;
            subsystems?: Record<string, unknown>;
        };
        expect(working.mode).toBe('working');
        expect(working.is_active).toBe(true);
        expect(working.subsystems).toHaveProperty('irrigation');
        expect(working.subsystems).toHaveProperty('diagnostics');
        expect(working.subsystems).toHaveProperty('lighting');
        expect(working.subsystems).toHaveProperty('zone_climate');
    });

    it('preserves existing command_plans while replacing subsystems', () => {
        const payload = profileToZoneLogicProfile(automationProfileDefaults, {
            active_mode: 'working',
            profiles: {
                working: {
                    mode: 'working',
                    is_active: true,
                    subsystems: { old: true },
                    command_plans: { startup: { steps: [] } },
                    created_at: '2026-01-01T00:00:00.000Z',
                    updated_at: '2026-01-01T00:00:00.000Z',
                },
            },
        });

        const working = (payload.profiles as Record<string, unknown>).working as {
            command_plans?: Record<string, unknown>;
            created_at?: string | null;
            subsystems?: Record<string, unknown>;
        };
        expect(working.command_plans).toEqual({ startup: { steps: [] } });
        expect(working.created_at).toBe('2026-01-01T00:00:00.000Z');
        expect(working.subsystems).not.toHaveProperty('old');
    });

    it('does not emit undefined values in canonical payload', () => {
        const payload = profileToZoneLogicProfile(automationProfileDefaults);
        expect(collectUndefinedPaths(payload)).toEqual([]);
    });

    it('round-trips drip/ph/ec defaults', () => {
        const payload = profileToZoneLogicProfile(automationProfileDefaults);
        const restored = zoneLogicProfileToProfile(payload);
        expect(restored.waterForm.systemType).toBe(automationProfileDefaults.waterForm.systemType);
        expect(restored.waterForm.intervalMinutes).toBe(automationProfileDefaults.waterForm.intervalMinutes);
        expect(restored.waterForm.durationSeconds).toBe(automationProfileDefaults.waterForm.durationSeconds);
        expect(restored.lightingForm.hoursOn).toBe(automationProfileDefaults.lightingForm.hoursOn);
    });
});

describe('bindingsResponseToAssignments', () => {
    it('maps binding_role → assignment_role using node_id', () => {
        const a = bindingsResponseToAssignments([
            { role: 'pump_main', node_id: 10, node_channel_id: 100 },
            { role: 'pump_acid', node_id: 20, node_channel_id: 200 },
        ]);
        expect(a.irrigation).toBe(10);
        expect(a.ph_correction).toBe(20);
        expect(a.ec_correction).toBeNull();
    });

    it('accepts {data: [...]} envelope', () => {
        const a = bindingsResponseToAssignments({
            data: [{ role: 'light_actuator', node_id: 99 }],
        });
        expect(a.light).toBe(99);
    });

    it('ignores unknown binding_roles', () => {
        const a = bindingsResponseToAssignments([
            { role: 'unknown_role', node_id: 7 },
        ]);
        expect(a.irrigation).toBeNull();
    });

    it('does not overwrite already-set assignment when same role appears twice', () => {
        const a = bindingsResponseToAssignments([
            { role: 'pump_a', node_id: 11, node_channel_id: 110 },
            { role: 'pump_b', node_id: 22, node_channel_id: 220 },
        ]);
        // Both pump_a и pump_b мапятся в ec_correction — берётся первый встреченный.
        expect(a.ec_correction).toBe(11);
    });
});

describe('assignmentsToApplyPayload', () => {
    it('emits only roles with positive ids', () => {
        const payload = assignmentsToApplyPayload(5, {
            irrigation: 10,
            ph_correction: 20,
            ec_correction: null,
            light: null,
            soil_moisture_sensor: null,
            co2_sensor: 0,
            co2_actuator: null,
            root_vent_actuator: null,
        } as never);
        expect(payload.zone_id).toBe(5);
        expect(payload.assignments).toEqual({
            irrigation: 10,
            ph_correction: 20,
        });
    });
});
