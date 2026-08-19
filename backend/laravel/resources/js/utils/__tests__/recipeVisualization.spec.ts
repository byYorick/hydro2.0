import { describe, expect, it } from 'vitest'
import {
  buildRecipePhaseVisuals,
  formatDurationHours,
  formatInterval,
  formatRangeValue,
  irrigationSystemLabel,
  summarizeRecipePhases,
} from '@/utils/recipeVisualization'

const phases = [
  {
    id: 1,
    phase_index: 0,
    name: 'Проращивание',
    duration_hours: 96,
    ph_target: 5.8,
    ph_min: 5.6,
    ph_max: 6.0,
    ec_target: 0.8,
    ec_min: 0.6,
    ec_max: 1.0,
    temp_air_target: 25.5,
    humidity_target: 90,
    co2_target: 550,
    lighting_photoperiod_hours: 18,
    lighting_start_time: '06:00:00',
    irrigation_mode: 'SUBSTRATE',
    irrigation_interval_sec: 900,
    irrigation_duration_sec: 20,
    nutrient_npk_ratio_pct: 44,
    nutrient_calcium_ratio_pct: 36,
    nutrient_magnesium_ratio_pct: 17,
    nutrient_micro_ratio_pct: 3,
    day_night_enabled: true,
    extensions: {
      temp_air_min: 24,
      temp_air_max: 27,
      humidity_min: 85,
      humidity_max: 95,
      lighting: { ppfd: 150 },
      day_night: {
        temperature: { day: 26, night: 24 },
        lighting: { day_hours: 18, day_start_time: '06:00:00' },
      },
      subsystems: { irrigation: { targets: { system_type: 'drip' } } },
    },
  },
  {
    id: 2,
    phase_index: 1,
    name: 'Вегетация',
    duration_days: 14,
    ph_target: 6.0,
    ec_target: 2.0,
    temp_air_target: 23,
    humidity_target: 70,
  },
]

describe('buildRecipePhaseVisuals', () => {
  it('считает накопительные границы фаз в днях', () => {
    const visuals = buildRecipePhaseVisuals(phases)

    expect(visuals).toHaveLength(2)
    expect(visuals[0].startDay).toBe(0)
    expect(visuals[0].endDay).toBe(4)
    expect(visuals[1].startDay).toBe(4)
    expect(visuals[1].endDay).toBe(18)
  })

  it('переводит duration_days в часы, когда duration_hours не задан', () => {
    const visuals = buildRecipePhaseVisuals(phases)

    expect(visuals[1].durationHours).toBe(336)
  })

  it('сортирует фазы по phase_index независимо от порядка входа', () => {
    const visuals = buildRecipePhaseVisuals([phases[1], phases[0]])

    expect(visuals.map((phase) => phase.name)).toEqual(['Проращивание', 'Вегетация'])
  })

  it('берёт коридоры температуры и влажности из extensions', () => {
    const [germination] = buildRecipePhaseVisuals(phases)

    expect(germination.temperature).toEqual({ target: 25.5, min: 24, max: 27 })
    expect(germination.humidity).toEqual({ target: 90, min: 85, max: 95 })
  })

  it('извлекает тип системы полива из extensions, если нет плоского поля', () => {
    const [germination] = buildRecipePhaseVisuals(phases)

    expect(germination.irrigation.systemType).toBe('drip')
  })

  it('собирает day/night и PPFD из extensions', () => {
    const [germination] = buildRecipePhaseVisuals(phases)

    expect(germination.dayNight.enabled).toBe(true)
    expect(germination.dayNight.temperature).toEqual({ day: 26, night: 24 })
    expect(germination.ppfd).toBe(150)
  })

  it('считает сумму долей питания', () => {
    const [germination] = buildRecipePhaseVisuals(phases)

    expect(germination.nutrition.ratioSum).toBe(100)
    expect(germination.nutrition.hasData).toBe(true)
  })

  it('нумерует фазы по порядку независимо от значений phase_index', () => {
    const visuals = buildRecipePhaseVisuals([
      { id: 1, phase_index: 5, name: 'Первая', duration_hours: 24 },
      { id: 2, phase_index: 9, name: 'Вторая', duration_hours: 24 },
    ])

    expect(visuals.map((phase) => phase.position)).toEqual([0, 1])
    expect(visuals.map((phase) => phase.index)).toEqual([5, 9])
  })

  it('возвращает пустой список для отсутствующих фаз', () => {
    expect(buildRecipePhaseVisuals(null)).toEqual([])
    expect(buildRecipePhaseVisuals([])).toEqual([])
  })

  it('читает day/night из корня, как во внутреннем состоянии редактора', () => {
    const [visual] = buildRecipePhaseVisuals([
      {
        phase_index: 0,
        name: 'Форма редактора',
        duration_hours: 24,
        day_night: { ph: { day: 5.9, night: 5.7 } },
      },
    ])

    expect(visual.dayNight.ph).toEqual({ day: 5.9, night: 5.7 })
  })
})

describe('summarizeRecipePhases', () => {
  it('суммирует длительность и сводит диапазоны параметров', () => {
    const summary = summarizeRecipePhases(buildRecipePhaseVisuals(phases))

    expect(summary.phaseCount).toBe(2)
    expect(summary.totalHours).toBe(432)
    expect(summary.totalDays).toBe(18)
    expect(summary.ph.min).toBe(5.6)
    expect(summary.ph.max).toBe(6)
    expect(summary.ec.min).toBe(0.6)
    expect(summary.ec.max).toBe(2)
    expect(summary.temperature.min).toBe(23)
    expect(summary.temperature.max).toBe(27)
  })

  it('возвращает пустую сводку без фаз', () => {
    const summary = summarizeRecipePhases([])

    expect(summary.phaseCount).toBe(0)
    expect(summary.totalHours).toBeNull()
    expect(summary.totalDays).toBeNull()
  })
})

describe('форматирование', () => {
  it('форматирует длительность в днях и часах', () => {
    expect(formatDurationHours(96)).toBe('4 дн')
    expect(formatDurationHours(100)).toBe('4 дн 4 ч')
    expect(formatDurationHours(12)).toBe('12 ч')
    expect(formatDurationHours(null)).toBe('—')
  })

  it('форматирует диапазон с единицами', () => {
    expect(formatRangeValue({ target: 5.8, min: 5.6, max: 6 }, '', 2)).toBe('5.6–6')
    expect(formatRangeValue({ target: 21, min: null, max: null }, '°C', 1)).toBe('21 °C')
    expect(formatRangeValue({ target: null, min: null, max: null })).toBe('—')
  })

  it('форматирует интервалы в подходящих единицах', () => {
    expect(formatInterval(30)).toBe('30 с')
    expect(formatInterval(900)).toBe('15 мин')
    expect(formatInterval(7200)).toBe('2 ч')
    expect(formatInterval(null)).toBe('—')
  })

  it('переводит код системы полива в читаемое название', () => {
    expect(irrigationSystemLabel('nft')).toBe('NFT')
    expect(irrigationSystemLabel('unknown_type')).toBe('unknown_type')
    expect(irrigationSystemLabel(null)).toBe('—')
  })
})
