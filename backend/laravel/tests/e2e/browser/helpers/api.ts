import { APIRequestContext } from '@playwright/test';

const baseURL = process.env.LARAVEL_URL || 'http://localhost:8081';

export interface TestGreenhouse {
  id: number;
  uid: string;
  name: string;
}

export interface TestRecipe {
  id: number;
  name: string;
  description?: string;
  plant_id?: number;
  latest_published_revision_id?: number | null;
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

export interface TestPlant {
  id: number;
  name: string;
}

export interface TestZone {
  id: number;
  name: string;
  status: string;
  greenhouse_id?: number;
}

export interface TestBinding {
  node_id: number;
  channel_id: number;
  role: string;
}

export class APITestHelper {
  constructor(
    private request: APIRequestContext, 
    private token?: string
  ) {}

  private async getHeaders(): Promise<Record<string, string>> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
      'X-Requested-With': 'XMLHttpRequest',
    };
    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }
    // Cookies автоматически передаются через storageState в APIRequestContext
    return headers;
  }

  async createTestGreenhouse(data?: Partial<TestGreenhouse>): Promise<TestGreenhouse> {
    const payload = {
      uid: data?.uid || `test-gh-${Date.now()}`,
      name: data?.name || `Test Greenhouse ${Date.now()}`,
      timezone: 'Europe/Moscow',
      type: 'indoor',
      ...data,
    };

    // Retry логика для rate limiting
    let lastError: Error | null = null;
    for (let attempt = 0; attempt < 5; attempt++) {
      if (attempt > 0) {
        // Ждем перед повтором (экспоненциальная задержка: 2s, 4s, 8s, 16s)
        const delay = Math.min(2000 * Math.pow(2, attempt - 1), 16000);
        await new Promise(resolve => setTimeout(resolve, delay));
      }

      const response = await this.request.post(`${baseURL}/api/greenhouses`, {
        headers: await this.getHeaders(),
        data: payload,
      });

      if (response.ok()) {
        const result = await response.json();
        return result.data;
      }

      const status = response.status();
      const text = await response.text();
      lastError = new Error(`Failed to create greenhouse: ${status} ${text}`);

      // Если это не rate limit, не повторяем
      if (status !== 429) {
        throw lastError;
      }
    }

    throw lastError || new Error('Failed to create greenhouse after retries');
  }

  async createTestPlant(data?: Partial<TestPlant>): Promise<TestPlant> {
    const payload = {
      name: data?.name || `Test Plant ${Date.now()}`,
      ...data,
    };

    const response = await this.request.post(`${baseURL}/api/plants`, {
      headers: await this.getHeaders(),
      data: payload,
    });

    if (!response.ok()) {
      throw new Error(`Failed to create plant: ${response.status()} ${await response.text()}`);
    }

    const result = await response.json();
    return result.data;
  }

  async createTestRecipe(data?: Partial<TestRecipe>, phases?: TestRecipePhase[]): Promise<TestRecipe> {
    const plantId = data?.plant_id ?? (await this.createTestPlant()).id;
    const payload = {
      name: data?.name || `Test Recipe ${Date.now()}`,
      description: data?.description || 'Test recipe description',
      plant_id: plantId,
    };

    const response = await this.request.post(`${baseURL}/api/recipes`, {
      headers: await this.getHeaders(),
      data: payload,
    });

    if (!response.ok()) {
      throw new Error(`Failed to create recipe: ${response.status()} ${await response.text()}`);
    }

    const result = await response.json();
    const recipe = result.data;

    const revisionResponse = await this.request.post(`${baseURL}/api/recipes/${recipe.id}/revisions`, {
      headers: await this.getHeaders(),
      data: { description: 'Initial revision' },
    });

    if (!revisionResponse.ok()) {
      throw new Error(`Failed to create recipe revision: ${revisionResponse.status()} ${await revisionResponse.text()}`);
    }

    const revisionResult = await revisionResponse.json();
    const revisionId = revisionResult.data?.id ?? revisionResult.id;

    if (!revisionId) {
      throw new Error('Recipe revision ID not found in response');
    }

    if (phases && phases.length > 0) {
      for (const phase of phases) {
        const phMin = typeof phase.ph_min === 'number' ? phase.ph_min : null;
        const phMax = typeof phase.ph_max === 'number' ? phase.ph_max : null;
        const ecMin = typeof phase.ec_min === 'number' ? phase.ec_min : null;
        const ecMax = typeof phase.ec_max === 'number' ? phase.ec_max : null;
        const phTarget = phMin !== null && phMax !== null ? (phMin + phMax) / 2 : (phMin ?? phMax);
        const ecTarget = ecMin !== null && ecMax !== null ? (ecMin + ecMax) / 2 : (ecMin ?? ecMax);

        const phaseResponse = await this.request.post(`${baseURL}/api/recipe-revisions/${revisionId}/phases`, {
          headers: await this.getHeaders(),
          data: {
            phase_index: phase.phase_index,
            name: phase.name,
            duration_hours: phase.duration_hours,
            ph_target: phTarget,
            ph_min: phMin,
            ph_max: phMax,
            ec_target: ecTarget,
            ec_min: ecMin,
            ec_max: ecMax,
            temp_air_target: phase.temp_air_target ?? null,
            humidity_target: phase.humidity_target ?? null,
            lighting_photoperiod_hours: phase.lighting_photoperiod_hours ?? null,
            irrigation_interval_sec: phase.irrigation_interval_sec ?? null,
            irrigation_duration_sec: phase.irrigation_duration_sec ?? null,
          },
        });

        if (!phaseResponse.ok()) {
          throw new Error(`Failed to create recipe phase: ${phaseResponse.status()} ${await phaseResponse.text()}`);
        }
      }
    }

    const publishResponse = await this.request.post(`${baseURL}/api/recipe-revisions/${revisionId}/publish`, {
      headers: await this.getHeaders(),
    });

    if (!publishResponse.ok()) {
      throw new Error(`Failed to publish recipe revision: ${publishResponse.status()} ${await publishResponse.text()}`);
    }

    return {
      ...recipe,
      plant_id: plantId,
      latest_published_revision_id: revisionId,
    };
  }

  async createTestZone(greenhouseId: number, data?: Partial<TestZone>): Promise<TestZone> {
    const payload = {
      greenhouse_id: greenhouseId,
      name: data?.name || `Test Zone ${Date.now()}`,
      description: data?.description || 'Test zone description',
      status: data?.status || 'PLANNED',
      ...data,
    };

    // Retry логика для rate limiting
    let lastError: Error | null = null;
    for (let attempt = 0; attempt < 5; attempt++) {
      if (attempt > 0) {
        // Ждем перед повтором (экспоненциальная задержка: 2s, 4s, 8s, 16s)
        const delay = Math.min(2000 * Math.pow(2, attempt - 1), 16000);
        await new Promise(resolve => setTimeout(resolve, delay));
      }

      const response = await this.request.post(`${baseURL}/api/zones`, {
        headers: await this.getHeaders(),
        data: payload,
      });

      if (response.ok()) {
        const result = await response.json();
        return result.data;
      }

      const status = response.status();
      const text = await response.text();
      lastError = new Error(`Failed to create zone: ${status} ${text}`);

      // Если это не rate limit, не повторяем
      if (status !== 429) {
        throw lastError;
      }
    }

    throw lastError || new Error('Failed to create zone after retries');
  }

  async attachRecipeToZone(zoneId: number, recipeId: number, startAt?: string): Promise<void> {
    const recipeResponse = await this.request.get(`${baseURL}/api/recipes/${recipeId}`, {
      headers: await this.getHeaders(),
    });

    if (!recipeResponse.ok()) {
      throw new Error(`Failed to load recipe: ${recipeResponse.status()} ${await recipeResponse.text()}`);
    }

    const recipeResult = await recipeResponse.json();
    const recipe = recipeResult.data ?? recipeResult;
    const revisionId = recipe.latest_published_revision_id || recipe.latest_draft_revision_id;
    const plantId = recipe.plants?.[0]?.id || recipe.plant_id;

    if (!revisionId) {
      throw new Error('Recipe revision ID not found');
    }

    if (!plantId) {
      throw new Error('Recipe plant ID not found');
    }

    const payload: Record<string, any> = {
      recipe_revision_id: revisionId,
      plant_id: plantId,
      start_immediately: false,
    };

    if (startAt) {
      payload.planting_at = startAt;
    }

    const response = await this.request.post(`${baseURL}/api/zones/${zoneId}/grow-cycles`, {
      headers: await this.getHeaders(),
      data: payload,
    });

    if (!response.ok()) {
      throw new Error(`Failed to attach recipe: ${response.status()} ${await response.text()}`);
    }
  }

  async createBinding(zoneId: number, nodeId: number, channelId: number, role: string): Promise<void> {
    const response = await this.request.post(`${baseURL}/api/zones/${zoneId}/infrastructure/bindings`, {
      headers: await this.getHeaders(),
      data: {
        node_id: nodeId,
        channel_id: channelId,
        role: role,
      },
    });

    if (!response.ok()) {
      throw new Error(`Failed to create binding: ${response.status()} ${await response.text()}`);
    }
  }

  private async getActiveGrowCycle(zoneId: number): Promise<any | null> {
    const response = await this.request.get(`${baseURL}/api/zones/${zoneId}/grow-cycle`, {
      headers: await this.getHeaders(),
    });

    if (!response.ok()) {
      return null;
    }

    const result = await response.json();
    return result.data ?? null;
  }

  async startZone(zoneId: number): Promise<void> {
    const cycle = await this.getActiveGrowCycle(zoneId);
    if (!cycle?.id) {
      throw new Error('No active grow cycle found for zone');
    }

    const response = await this.request.post(`${baseURL}/api/grow-cycles/${cycle.id}/start`, {
      headers: await this.getHeaders(),
    });

    if (!response.ok()) {
      throw new Error(`Failed to start zone: ${response.status()} ${await response.text()}`);
    }
  }

  async pauseZone(zoneId: number): Promise<void> {
    const cycle = await this.getActiveGrowCycle(zoneId);
    if (!cycle?.id) {
      throw new Error('No active grow cycle found for zone');
    }

    const response = await this.request.post(`${baseURL}/api/grow-cycles/${cycle.id}/pause`, {
      headers: await this.getHeaders(),
    });

    if (!response.ok()) {
      throw new Error(`Failed to pause zone: ${response.status()} ${await response.text()}`);
    }
  }

  async resumeZone(zoneId: number): Promise<void> {
    const cycle = await this.getActiveGrowCycle(zoneId);
    if (!cycle?.id) {
      throw new Error('No active grow cycle found for zone');
    }

    const response = await this.request.post(`${baseURL}/api/grow-cycles/${cycle.id}/resume`, {
      headers: await this.getHeaders(),
    });

    if (!response.ok()) {
      throw new Error(`Failed to resume zone: ${response.status()} ${await response.text()}`);
    }
  }

  async harvestZone(zoneId: number): Promise<void> {
    const cycle = await this.getActiveGrowCycle(zoneId);
    if (!cycle?.id) {
      throw new Error('No active grow cycle found for zone');
    }

    const response = await this.request.post(`${baseURL}/api/grow-cycles/${cycle.id}/harvest`, {
      headers: await this.getHeaders(),
    });

    if (!response.ok()) {
      throw new Error(`Failed to harvest zone: ${response.status()} ${await response.text()}`);
    }
  }

  async getZone(zoneId: number): Promise<TestZone> {
    const response = await this.request.get(`${baseURL}/api/zones/${zoneId}`, {
      headers: await this.getHeaders(),
    });

    if (!response.ok()) {
      throw new Error(`Failed to get zone: ${response.status()} ${await response.text()}`);
    }

    const result = await response.json();
    return result.data;
  }

  async deleteGreenhouse(id: number): Promise<void> {
    const response = await this.request.delete(`${baseURL}/api/greenhouses/${id}`, {
      headers: await this.getHeaders(),
    });

    if (!response.ok() && response.status() !== 404) {
      throw new Error(`Failed to delete greenhouse: ${response.status()} ${await response.text()}`);
    }
  }

  async deleteRecipe(id: number): Promise<void> {
    const response = await this.request.delete(`${baseURL}/api/recipes/${id}`, {
      headers: await this.getHeaders(),
    });

    if (!response.ok() && response.status() !== 404) {
      throw new Error(`Failed to delete recipe: ${response.status()} ${await response.text()}`);
    }
  }

  async deleteZone(id: number): Promise<void> {
    const response = await this.request.delete(`${baseURL}/api/zones/${id}`, {
      headers: await this.getHeaders(),
    });

    if (!response.ok() && response.status() !== 404) {
      throw new Error(`Failed to delete zone: ${response.status()} ${await response.text()}`);
    }
  }

  async cleanupTestData(ids: {
    greenhouses?: number[];
    recipes?: number[];
    zones?: number[];
  }): Promise<void> {
    // Удаляем в обратном порядке зависимостей
    if (ids.zones) {
      for (const zoneId of ids.zones) {
        await this.deleteZone(zoneId).catch(() => {});
      }
    }
    if (ids.recipes) {
      for (const recipeId of ids.recipes) {
        await this.deleteRecipe(recipeId).catch(() => {});
      }
    }
    if (ids.greenhouses) {
      for (const greenhouseId of ids.greenhouses) {
        await this.deleteGreenhouse(greenhouseId).catch(() => {});
      }
    }
  }
}
