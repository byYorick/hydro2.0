export type IrrigationSystem = 'drip' | 'substrate_trays' | 'nft'

export interface ClimateFormState {
  enabled: boolean
  dayTemp: number
  nightTemp: number
  dayHumidity: number
  nightHumidity: number
  intervalMinutes: number
  dayStart: string
  nightStart: string
  ventMinPercent: number
  ventMaxPercent: number
  useExternalTelemetry: boolean
  outsideTempMin: number
  outsideTempMax: number
  outsideHumidityMax: number
  manualOverrideEnabled: boolean
  overrideMinutes: number
}

export interface WaterFormState {
  systemType: IrrigationSystem
  tanksCount: number
  cleanTankFillL: number
  nutrientTankTargetL: number
  irrigationBatchL: number
  intervalMinutes: number
  durationSeconds: number
  fillTemperatureC: number
  fillWindowStart: string
  fillWindowEnd: string
  targetPh: number
  targetEc: number
  valveSwitching: boolean
  correctionDuringIrrigation: boolean
  enableDrainControl: boolean
  drainTargetPercent: number
  diagnosticsEnabled: boolean
  diagnosticsIntervalMinutes: number
  cycleStartWorkflowEnabled: boolean
  cleanTankFullThreshold: number
  refillDurationSeconds: number
  refillTimeoutSeconds: number
  refillRequiredNodeTypes: string
  refillPreferredChannel: string
  solutionChangeEnabled: boolean
  solutionChangeIntervalMinutes: number
  solutionChangeDurationSeconds: number
  manualIrrigationSeconds: number
}

export interface LightingFormState {
  enabled: boolean
  luxDay: number
  luxNight: number
  hoursOn: number
  intervalMinutes: number
  scheduleStart: string
  scheduleEnd: string
  manualIntensity: number
  manualDurationHours: number
}

export interface ZoneAutomationForms {
  climateForm: ClimateFormState
  waterForm: WaterFormState
  lightingForm: LightingFormState
}
