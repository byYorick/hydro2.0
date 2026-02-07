export type Mode = 'select' | 'create'
export type SystemType = 'drip' | 'substrate_trays' | 'nft'

export interface Greenhouse {
  id: number
  uid: string
  name: string
  type?: string
  greenhouse_type_id?: number | null
  greenhouse_type?: GreenhouseType | null
  description?: string
}

export interface GreenhouseType {
  id: number
  code: string
  name: string
  description?: string | null
}

export interface Zone {
  id: number
  name: string
  greenhouse_id: number
}

export interface Plant {
  id: number
  name: string
}

export interface Recipe {
  id: number
  name: string
  phases_count?: number
  phases?: RecipePhase[]
  plants?: Array<{
    id: number
    name?: string
  }>
}

export interface RecipePhase {
  id?: number
  phase_index: number
  name?: string
  ph_target?: number | null
  ec_target?: number | null
  temp_air_target?: number | null
  humidity_target?: number | null
  lighting_photoperiod_hours?: number | null
  irrigation_mode?: 'SUBSTRATE' | 'RECIRC' | string | null
  irrigation_interval_sec?: number | null
  irrigation_duration_sec?: number | null
  extensions?: {
    day_night?: {
      temperature?: {
        day?: number | null
        night?: number | null
      }
      humidity?: {
        day?: number | null
        night?: number | null
      }
    }
  } | null
}

export interface Node {
  id: number
  uid?: string
  name?: string
  type?: string
}

export interface RecipePhaseTargets {
  ph: number
  ec: number
  temp_air: number
  humidity_air: number
  light_hours: number
  irrigation_interval_sec: number
  irrigation_duration_sec: number
}

export interface RecipePhaseForm {
  phase_index: number
  name: string
  duration_hours: number
  targets: RecipePhaseTargets
}

export interface SetupWizardLoadingState {
  greenhouses: boolean
  zones: boolean
  plants: boolean
  recipes: boolean
  nodes: boolean
  stepGreenhouse: boolean
  stepZone: boolean
  stepPlant: boolean
  stepRecipe: boolean
  stepDevices: boolean
  stepAutomation: boolean
  stepLaunch: boolean
}

export interface GreenhouseFormState {
  name: string
  timezone: string
  greenhouse_type_id: number | null
  description: string
}

export interface ZoneFormState {
  name: string
  description: string
}

export interface PlantFormState {
  name: string
  species: string
  variety: string
}

export interface RecipeFormState {
  name: string
  description: string
  phases: RecipePhaseForm[]
}

export interface AutomationFormState {
  systemType: SystemType
  manageClimate: boolean
  manageLighting: boolean
  targetPh: number
  targetEc: number
  dayTemp: number
  dayHumidity: number
  ventMinPercent: number
  ventMaxPercent: number
  luxDay: number
  intervalMinutes: number
  durationSeconds: number
  cleanTankFillL: number
  nutrientTankFillL: number
  drainTargetPercent: number
}
