import { APIRequestContext } from '@playwright/test';

const baseURL = process.env.LARAVEL_URL || 'http://localhost:80';

export interface TestGreenhouse {
  id: number;
  uid: string;
  name: string;
}

export interface TestRecipe {
  id: number;
  name: string;
  description?: string;
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

    const response = await this.request.post(`${baseURL}/api/greenhouses`, {
      headers: await this.getHeaders(),
      data: payload,
    });

    if (!response.ok()) {
      throw new Error(`Failed to create greenhouse: ${response.status()} ${await response.text()}`);
    }

    const result = await response.json();
    return result.data;
  }

  async createTestRecipe(data?: Partial<TestRecipe>, phases?: TestRecipePhase[]): Promise<TestRecipe> {
    const payload = {
      name: data?.name || `Test Recipe ${Date.now()}`,
      description: data?.description || 'Test recipe description',
      ...data,
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

    // Создаем фазы, если они указаны
    if (phases && phases.length > 0) {
      for (const phase of phases) {
        await this.request.post(`${baseURL}/api/recipes/${recipe.id}/phases`, {
          headers: await this.getHeaders(),
          data: phase,
        });
      }
    }

    return recipe;
  }

  async createTestZone(greenhouseId: number, data?: Partial<TestZone>): Promise<TestZone> {
    const payload = {
      greenhouse_id: greenhouseId,
      name: data?.name || `Test Zone ${Date.now()}`,
      description: data?.description || 'Test zone description',
      status: data?.status || 'PLANNED',
      ...data,
    };

    const response = await this.request.post(`${baseURL}/api/zones`, {
      headers: await this.getHeaders(),
      data: payload,
    });

    if (!response.ok()) {
      throw new Error(`Failed to create zone: ${response.status()} ${await response.text()}`);
    }

    const result = await response.json();
    return result.data;
  }

  async attachRecipeToZone(zoneId: number, recipeId: number, startAt?: string): Promise<void> {
    const payload: any = { recipe_id: recipeId };
    if (startAt) {
      payload.start_at = startAt;
    }

    const response = await this.request.post(`${baseURL}/api/zones/${zoneId}/attach-recipe`, {
      headers: await this.getHeaders(),
      data: payload,
    });

    if (!response.ok()) {
      throw new Error(`Failed to attach recipe: ${response.status()} ${await response.text()}`);
    }
  }

  async createBinding(zoneId: number, nodeId: number, channelId: number, role: string): Promise<void> {
    const response = await this.request.post(`${baseURL}/api/zones/${zoneId}/bindings`, {
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

  async startZone(zoneId: number): Promise<void> {
    const response = await this.request.post(`${baseURL}/api/zones/${zoneId}/start`, {
      headers: await this.getHeaders(),
    });

    if (!response.ok()) {
      throw new Error(`Failed to start zone: ${response.status()} ${await response.text()}`);
    }
  }

  async pauseZone(zoneId: number): Promise<void> {
    const response = await this.request.post(`${baseURL}/api/zones/${zoneId}/pause`, {
      headers: await this.getHeaders(),
    });

    if (!response.ok()) {
      throw new Error(`Failed to pause zone: ${response.status()} ${await response.text()}`);
    }
  }

  async resumeZone(zoneId: number): Promise<void> {
    const response = await this.request.post(`${baseURL}/api/zones/${zoneId}/resume`, {
      headers: await this.getHeaders(),
    });

    if (!response.ok()) {
      throw new Error(`Failed to resume zone: ${response.status()} ${await response.text()}`);
    }
  }

  async startZone(zoneId: number): Promise<void> {
    const response = await this.request.post(`${baseURL}/api/zones/${zoneId}/start`, {
      headers: await this.getHeaders(),
    });

    if (!response.ok()) {
      throw new Error(`Failed to start zone: ${response.status()} ${await response.text()}`);
    }
  }

  async pauseZone(zoneId: number): Promise<void> {
    const response = await this.request.post(`${baseURL}/api/zones/${zoneId}/pause`, {
      headers: await this.getHeaders(),
    });

    if (!response.ok()) {
      throw new Error(`Failed to pause zone: ${response.status()} ${await response.text()}`);
    }
  }

  async resumeZone(zoneId: number): Promise<void> {
    const response = await this.request.post(`${baseURL}/api/zones/${zoneId}/resume`, {
      headers: await this.getHeaders(),
    });

    if (!response.ok()) {
      throw new Error(`Failed to resume zone: ${response.status()} ${await response.text()}`);
    }
  }

  async harvestZone(zoneId: number): Promise<void> {
    const response = await this.request.post(`${baseURL}/api/zones/${zoneId}/harvest`, {
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

