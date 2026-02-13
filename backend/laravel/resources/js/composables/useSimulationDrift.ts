import { reactive, ref } from 'vue'

export interface SimulationInitialState {
  ph: number | null
  ec: number | null
  temp_air: number | null
  temp_water: number | null
  humidity_air: number | null
}

type DriftKey = keyof SimulationInitialState
type DriftTouchedKey = DriftKey | 'noise'

const DRIFT_RELATIVE_RATES: Record<DriftKey, number> = {
  ph: 0.04,
  ec: 0.07,
  temp_air: 0.002,
  temp_water: 0.002,
  humidity_air: 0.002,
}

const DRIFT_PRESETS = {
  aggressive: {
    ph: 0.24,
    ec: 0.105,
    temp_air: 0.004,
    temp_water: 0.004,
    humidity_air: 0.004,
    noise: 0.02,
  },
} as const

function roundDrift(value: number, precision = 3): number {
  const factor = 10 ** precision
  return Math.round(value * factor) / factor
}

export function useSimulationDrift(initialState: SimulationInitialState) {
  const driftPh = ref<number | null>(null)
  const driftEc = ref<number | null>(null)
  const driftTempAir = ref<number | null>(null)
  const driftTempWater = ref<number | null>(null)
  const driftHumidity = ref<number | null>(null)
  const driftNoise = ref<number | null>(null)

  const driftTouched = reactive({
    ph: false,
    ec: false,
    temp_air: false,
    temp_water: false,
    humidity_air: false,
    noise: false,
  })

  const markDriftTouched = (key: DriftTouchedKey): void => {
    driftTouched[key] = true
  }

  const applyAutoDrift = (): void => {
    const driftMap = {
      ph: driftPh,
      ec: driftEc,
      temp_air: driftTempAir,
      temp_water: driftTempWater,
      humidity_air: driftHumidity,
    } as const

    ;(Object.keys(DRIFT_RELATIVE_RATES) as DriftKey[]).forEach((key) => {
      if (driftTouched[key]) return
      const baseValue = initialState[key]
      if (baseValue === null || baseValue === undefined) {
        driftMap[key].value = null
        return
      }
      driftMap[key].value = roundDrift(baseValue * DRIFT_RELATIVE_RATES[key])
    })

    if (!driftTouched.noise && driftNoise.value === null) {
      const values = Object.values(driftMap)
        .map((refValue) => refValue.value)
        .filter((value): value is number => typeof value === 'number' && !Number.isNaN(value))
      if (values.length) {
        const maxAbs = Math.max(...values.map((value) => Math.abs(value)))
        if (maxAbs > 0) {
          driftNoise.value = roundDrift(maxAbs * 0.1)
        }
      }
    }
  }

  const applyAggressiveDrift = (): void => {
    const preset = DRIFT_PRESETS.aggressive
    driftPh.value = preset.ph
    driftEc.value = preset.ec
    driftTempAir.value = preset.temp_air
    driftTempWater.value = preset.temp_water
    driftHumidity.value = preset.humidity_air
    driftNoise.value = preset.noise
    driftTouched.ph = true
    driftTouched.ec = true
    driftTouched.temp_air = true
    driftTouched.temp_water = true
    driftTouched.humidity_air = true
    driftTouched.noise = true
  }

  const resetDriftValues = (): void => {
    driftPh.value = null
    driftEc.value = null
    driftTempAir.value = null
    driftTempWater.value = null
    driftHumidity.value = null
    driftNoise.value = null
    driftTouched.ph = false
    driftTouched.ec = false
    driftTouched.temp_air = false
    driftTouched.temp_water = false
    driftTouched.humidity_air = false
    driftTouched.noise = false
    applyAutoDrift()
  }

  return {
    driftPh,
    driftEc,
    driftTempAir,
    driftTempWater,
    driftHumidity,
    driftNoise,
    driftTouched,
    markDriftTouched,
    applyAutoDrift,
    applyAggressiveDrift,
    resetDriftValues,
  }
}
