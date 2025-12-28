export interface TestZone {
  id: number;
  name: string;
  status: string;
  greenhouse_id?: number;
}

export interface TestRecipe {
  id: number;
  name: string;
  description?: string;
  plant_id?: number;
  latest_published_revision_id?: number | null;
}

export interface TestBinding {
  node_id: number;
  channel_id: number;
  role: string;
}

export interface TestGreenhouse {
  id: number;
  uid: string;
  name: string;
}

export interface TestRecipePhase {
  phase_index: number;
  name: string;
  duration_hours: number;
  ph_min?: number;
  ph_max?: number;
  ec_min?: number;
  ec_max?: number;
  temp_air_target?: number;
  humidity_target?: number;
  lighting_photoperiod_hours?: number;
  irrigation_interval_sec?: number;
  irrigation_duration_sec?: number;
}
