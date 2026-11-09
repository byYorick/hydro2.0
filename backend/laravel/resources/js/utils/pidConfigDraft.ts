import type { PidConfig } from '@/types/PidConfig'

/** Same bounds as schemas/zone_pid.v1.json; the server remains authoritative. */
export function pidConfigError(config: PidConfig): string | null {
  for (const [key, max] of Object.entries({ dead_zone: 10, close_zone: 20, far_zone: 50, max_integral: 500 })) {
    const value = config[key as keyof PidConfig]
    if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0 || value > max) return `${key}: введите число больше 0 и не больше ${max}.`
  }
  if (config.close_zone <= config.dead_zone || config.far_zone <= config.close_zone) return 'Зоны должны возрастать: мёртвая < близкая < дальняя.'
  for (const zone of ['close', 'far'] as const) {
    for (const [key, max] of Object.entries({ kp: 1000, ki: 100, kd: 100 })) {
      const value = config.zone_coeffs[zone][key as 'kp' | 'ki' | 'kd']
      if (typeof value !== 'number' || !Number.isFinite(value) || value < 0 || value > max) return `${zone}.${key}: введите число от 0 до ${max}.`
    }
  }
  return null
}

export const DEFAULT_CONFIGS: Record<'ph' | 'ec', PidConfig> = {
  ph: {
    dead_zone: 0.04,
    close_zone: 0.18,
    far_zone: 0.65,
    zone_coeffs: {
      close: { kp: 0.18, ki: 0.01, kd: 0.0 },
      far: { kp: 0.28, ki: 0.015, kd: 0.0 },
    },
    max_integral: 12.0,
  },
  ec: {
    dead_zone: 0.06,
    close_zone: 0.25,
    far_zone: 0.9,
    zone_coeffs: {
      close: { kp: 0.35, ki: 0.02, kd: 0.0 },
      far: { kp: 0.55, ki: 0.03, kd: 0.0 },
    },
    max_integral: 20.0,
  },
}

export function cloneConfig(config: PidConfig): PidConfig {
  return JSON.parse(JSON.stringify(config)) as PidConfig
}

function toNumberOr(value: unknown, fallback: number): number {
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : fallback
}

export function normalizeConfig(raw: Partial<PidConfig> | null | undefined, type: 'ph' | 'ec'): PidConfig {
  const defaults = DEFAULT_CONFIGS[type]
  const closeRaw: Partial<PidConfig['zone_coeffs']['close']> = raw?.zone_coeffs?.close ?? {}
  const farRaw: Partial<PidConfig['zone_coeffs']['far']> = raw?.zone_coeffs?.far ?? {}

  return {
    dead_zone: toNumberOr(raw?.dead_zone, defaults.dead_zone),
    close_zone: toNumberOr(raw?.close_zone, defaults.close_zone),
    far_zone: toNumberOr(raw?.far_zone, defaults.far_zone),
    zone_coeffs: {
      close: {
        kp: toNumberOr(closeRaw.kp, defaults.zone_coeffs.close.kp),
        ki: toNumberOr(closeRaw.ki, defaults.zone_coeffs.close.ki),
        kd: toNumberOr(closeRaw.kd, defaults.zone_coeffs.close.kd),
      },
      far: {
        kp: toNumberOr(farRaw.kp, defaults.zone_coeffs.far.kp),
        ki: toNumberOr(farRaw.ki, defaults.zone_coeffs.far.ki),
        kd: toNumberOr(farRaw.kd, defaults.zone_coeffs.far.kd),
      },
    },
    max_integral: toNumberOr(raw?.max_integral, defaults.max_integral),
  }
}
