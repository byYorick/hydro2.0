import { z } from 'zod';

function requiredPositiveInt(message: string) {
    return z
        .number({
            error: (issue) => (
                issue.input === undefined || issue.input === null
                    ? message
                    : 'Ожидается числовой идентификатор.'
            ),
        })
        .int('Ожидается целочисленный идентификатор.')
        .positive(message);
}

const irrigationOverrideSchema = z
    .object({
        mode: z.enum(['TIME', 'MOISTURE', 'TASK']).optional(),
        interval_sec: z.number().int().min(60).max(86_400).optional(),
        duration_sec: z.number().int().min(1).max(3_600).optional(),
    })
    .strict();

const correctionOverrideSchema = z
    .object({
        target_ph: z.number().min(3).max(9).optional(),
        target_ec: z.number().min(0).max(10).optional(),
        tolerance_ph: z.number().min(0).max(2).optional(),
        tolerance_ec: z.number().min(0).max(2).optional(),
    })
    .strict();

const climateOverrideSchema = z
    .object({
        day_air_temp_c: z.number().min(-10).max(60).optional(),
        night_air_temp_c: z.number().min(-10).max(60).optional(),
        humidity_pct: z.number().min(0).max(100).optional(),
        co2_ppm: z.number().int().min(0).max(5_000).optional(),
    })
    .strict();

const lightingOverrideSchema = z
    .object({
        photoperiod_hours: z.number().int().min(0).max(24).optional(),
        start_time: z
            .string()
            .regex(/^([01]\d|2[0-3]):[0-5]\d$/, 'HH:MM format expected')
            .optional(),
        intensity_pct: z.number().min(0).max(100).optional(),
    })
    .strict();

export const overridesSchema = z
    .object({
        irrigation: irrigationOverrideSchema.optional(),
        correction: correctionOverrideSchema.optional(),
        climate: climateOverrideSchema.optional(),
        lighting: lightingOverrideSchema.optional(),
    })
    .strict();

export const bindingsSchema = z
    .object({
        soil_moisture_sensor_id: z.number().int().positive().optional(),
        ph_sensor_node_id: z.number().int().positive().optional(),
        ec_sensor_node_id: z.number().int().positive().optional(),
        irrigation_pump_node_id: z.number().int().positive().optional(),
        ph_pump_node_id: z.number().int().positive().optional(),
        ec_pump_node_id: z.number().int().positive().optional(),
    })
    .strict();

export const growCycleLaunchSchema = z
    .object({
        zone_id: requiredPositiveInt('Выберите зону.'),
        recipe_revision_id: requiredPositiveInt('Выберите опубликованную ревизию рецепта.'),
        plant_id: requiredPositiveInt('Выберите растение.'),
        planting_at: z
            .string({
                error: (issue) => (
                    issue.input === undefined || issue.input === null
                        ? 'Укажите дату и время посадки.'
                        : 'Дата посадки должна быть строкой.'
                ),
            })
            .refine((value) => !Number.isNaN(Date.parse(value)), {
                message: 'Укажите корректную дату и время посадки.',
            }),
        batch_label: z.string().trim().max(100).optional(),
        notes: z.string().trim().max(2_000).optional(),
        overrides: overridesSchema.optional(),
        bindings: bindingsSchema.optional(),
        idempotency_key: z.string().uuid().optional(),
    })
    .strict();

export type GrowCycleLaunchPayload = z.infer<typeof growCycleLaunchSchema>;
export type GrowCycleLaunchOverrides = z.infer<typeof overridesSchema>;
export type GrowCycleLaunchBindings = z.infer<typeof bindingsSchema>;

export const emptyGrowCycleLaunch: Partial<GrowCycleLaunchPayload> = {
    overrides: {},
    bindings: {},
};
