import { describe, expect, it } from 'vitest';
import {
    assignmentsToApplyPayload,
    bindingsResponseToAssignments,
    profileToZoneLogicProfile,
    zoneLogicProfileToProfile,
} from '../automationProfileConverters';
import { automationProfileDefaults } from '@/schemas/automationProfile';

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

    it('accepts plain number strings', () => {
        const profile = zoneLogicProfileToProfile({
            water: { clean_tank_fill_l: '200', nutrient_tank_target_l: '180' },
        });
        expect(profile.waterForm.cleanTankFillL).toBe(200);
        expect(profile.waterForm.nutrientTankTargetL).toBe(180);
    });
});

describe('profileToZoneLogicProfile', () => {
    it('emits water/lighting/zone_climate top-level keys', () => {
        const payload = profileToZoneLogicProfile(automationProfileDefaults);
        expect(payload).toHaveProperty('water');
        expect(payload).toHaveProperty('lighting');
        expect(payload).toHaveProperty('zone_climate');
    });

    it('round-trips drip/ph/ec defaults', () => {
        const payload = profileToZoneLogicProfile(automationProfileDefaults);
        const restored = zoneLogicProfileToProfile(payload);
        expect(restored.waterForm.systemType).toBe(automationProfileDefaults.waterForm.systemType);
        expect(restored.waterForm.targetPh).toBe(automationProfileDefaults.waterForm.targetPh);
        expect(restored.waterForm.targetEc).toBe(automationProfileDefaults.waterForm.targetEc);
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
