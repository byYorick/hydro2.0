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
  targets: {
    ph?: number;
    ec?: number;
    temp_air?: number;
    humidity_air?: number;
    light_hours?: number;
    irrigation_interval_sec?: number;
    irrigation_duration_sec?: number;
  };
}

