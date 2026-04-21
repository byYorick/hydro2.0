import { describe, expect, it } from 'vitest';
import { bindingsSchema, growCycleLaunchSchema, overridesSchema } from '../growCycleLaunch';

describe('growCycleLaunchSchema', () => {
    const base = {
        zone_id: 5,
        recipe_revision_id: 10,
        plant_id: 3,
        planting_at: '2026-04-18T10:00:00Z',
    };

    it('accepts minimal valid payload', () => {
        const parsed = growCycleLaunchSchema.safeParse(base);
        expect(parsed.success).toBe(true);
    });

    it('requires positive zone_id', () => {
        const parsed = growCycleLaunchSchema.safeParse({ ...base, zone_id: 0 });
        expect(parsed.success).toBe(false);
        if (!parsed.success) {
            expect(parsed.error.issues[0]?.path).toEqual(['zone_id']);
        }
    });

    it('requires positive recipe_revision_id', () => {
        const parsed = growCycleLaunchSchema.safeParse({ ...base, recipe_revision_id: -1 });
        expect(parsed.success).toBe(false);
    });

    it('rejects non-parsable planting_at', () => {
        const parsed = growCycleLaunchSchema.safeParse({ ...base, planting_at: 'not-a-date' });
        expect(parsed.success).toBe(false);
    });

    it('accepts overrides with valid irrigation block', () => {
        const parsed = growCycleLaunchSchema.safeParse({
            ...base,
            overrides: { irrigation: { mode: 'TIME', interval_sec: 600, duration_sec: 15 } },
        });
        expect(parsed.success).toBe(true);
    });

    it('rejects irrigation interval below floor', () => {
        const parsed = growCycleLaunchSchema.safeParse({
            ...base,
            overrides: { irrigation: { interval_sec: 30 } },
        });
        expect(parsed.success).toBe(false);
    });

    it('rejects unknown irrigation mode', () => {
        const parsed = growCycleLaunchSchema.safeParse({
            ...base,
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            overrides: { irrigation: { mode: 'CHAOS' as any } },
        });
        expect(parsed.success).toBe(false);
    });

    it('rejects correction target_ph outside bounds', () => {
        const parsed = growCycleLaunchSchema.safeParse({
            ...base,
            overrides: { correction: { target_ph: 12 } },
        });
        expect(parsed.success).toBe(false);
    });

    it('rejects non-HH:MM lighting.start_time', () => {
        const parsed = growCycleLaunchSchema.safeParse({
            ...base,
            overrides: { lighting: { start_time: '25:70' } },
        });
        expect(parsed.success).toBe(false);
    });

    it('trims and caps batch_label length', () => {
        const parsed = growCycleLaunchSchema.safeParse({ ...base, batch_label: 'x'.repeat(500) });
        expect(parsed.success).toBe(false);
    });

    it('strips unknown top-level keys (strict mode)', () => {
        const parsed = growCycleLaunchSchema.safeParse({ ...base, extra_field: 'evil' });
        expect(parsed.success).toBe(false);
    });

    it('accepts optional bindings block', () => {
        const parsed = growCycleLaunchSchema.safeParse({
            ...base,
            bindings: { soil_moisture_sensor_id: 1, irrigation_pump_node_id: 2 },
        });
        expect(parsed.success).toBe(true);
    });

    it('rejects bindings with negative ids', () => {
        const parsed = growCycleLaunchSchema.safeParse({
            ...base,
            bindings: { soil_moisture_sensor_id: -1 },
        });
        expect(parsed.success).toBe(false);
    });
});

describe('overridesSchema', () => {
    it('accepts empty object', () => {
        expect(overridesSchema.safeParse({}).success).toBe(true);
    });

    it('rejects unknown top-level keys', () => {
        expect(overridesSchema.safeParse({ magic: { ok: 1 } }).success).toBe(false);
    });

    it('accepts partial climate block', () => {
        expect(
            overridesSchema.safeParse({ climate: { day_air_temp_c: 24 } }).success,
        ).toBe(true);
    });

    it('rejects climate.co2_ppm below 0', () => {
        expect(overridesSchema.safeParse({ climate: { co2_ppm: -10 } }).success).toBe(false);
    });
});

describe('bindingsSchema', () => {
    it('accepts empty object', () => {
        expect(bindingsSchema.safeParse({}).success).toBe(true);
    });

    it('rejects unknown keys', () => {
        expect(bindingsSchema.safeParse({ foo: 1 }).success).toBe(false);
    });
});
