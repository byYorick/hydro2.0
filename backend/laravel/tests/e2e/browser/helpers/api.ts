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

  private async getActiveCycle(zoneId: number, maxAttempts = 3): Promise<any | null> {
    const headers = await this.getHeaders();
    let lastError: Error | null = null;
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      const response = await this.request.get(`${baseURL}/api/zones/${zoneId}/grow-cycle`, { headers });
      if (response.ok()) {
        const data = await response.json();
        const payload = data.data;
        const cycle = payload?.cycle ?? payload;
        return cycle?.id ? cycle : null;
      }

      const status = response.status();
      const text = await response.text();
      lastError = new Error(`Failed to get grow cycle: ${status} ${text}`);
      if (status !== 429) {
        throw lastError;
      }

      const retryAfterHeader = response.headers()['retry-after'];
      const retryAfter = retryAfterHeader ? Number(retryAfterHeader) : 0;
      const delay = Number.isFinite(retryAfter) && retryAfter > 0
        ? retryAfter * 1000
        : Math.min(2000 * Math.pow(2, attempt), 16000);
      await new Promise(resolve => setTimeout(resolve, delay));
    }

    throw lastError || new Error('Failed to get grow cycle after retries');
  }

  private async postWithRetry(url: string, label: string, data?: Record<string, any>, maxAttempts = 3): Promise<void> {
    const headers = await this.getHeaders();
    let lastError: Error | null = null;
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      const response = await this.request.post(url, {
        headers,
        data,
      });
      if (response.ok()) {
        return;
      }

      const status = response.status();
      const text = await response.text();
      lastError = new Error(`Failed to ${label}: ${status} ${text}`);
      if (status !== 429) {
        throw lastError;
      }

      const retryAfterHeader = response.headers()['retry-after'];
      const retryAfter = retryAfterHeader ? Number(retryAfterHeader) : 0;
      const delay = Number.isFinite(retryAfter) && retryAfter > 0
        ? retryAfter * 1000
        : Math.min(2000 * Math.pow(2, attempt), 16000);
      await new Promise(resolve => setTimeout(resolve, delay));
    }

    throw lastError || new Error(`Failed to ${label} after retries`);
  }

  private async postJsonWithRetry(
    url: string,
    label: string,
    data?: Record<string, any>,
    maxAttempts = 3
  ): Promise<any> {
    const headers = await this.getHeaders();
    let lastError: Error | null = null;
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      const response = await this.request.post(url, {
        headers,
        data,
      });

      if (response.ok()) {
        return response.json();
      }

      const status = response.status();
      const text = await response.text();
      lastError = new Error(`Failed to ${label}: ${status} ${text}`);
      if (status !== 429) {
        throw lastError;
      }

      const retryAfterHeader = response.headers()['retry-after'];
      const retryAfter = retryAfterHeader ? Number(retryAfterHeader) : 0;
      const delay = Number.isFinite(retryAfter) && retryAfter > 0
        ? retryAfter * 1000
        : Math.min(2000 * Math.pow(2, attempt), 16000);
      await new Promise(resolve => setTimeout(resolve, delay));
    }

    throw lastError || new Error(`Failed to ${label} after retries`);
  }

  private async ensurePlantId(): Promise<number> {
    const headers = await this.getHeaders();
    const plantsResponse = await this.request.get(`${baseURL}/api/plants`, { headers });
    if (plantsResponse.ok()) {
      const plantsData = await plantsResponse.json();
      if (plantsData.data && plantsData.data.length > 0) {
        return plantsData.data[0].id;
      }
    }

    const createPlantResponse = await this.request.post(`${baseURL}/api/plants`, {
      headers,
      data: {
        name: `Test Plant ${Date.now()}`,
        scientific_name: 'Test Plant',
      },
    });

    if (!createPlantResponse.ok()) {
      throw new Error(`Failed to create plant: ${createPlantResponse.status()} ${await createPlantResponse.text()}`);
    }

    const plantData = await createPlantResponse.json();
    return plantData.data.id;
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

  async createTestRecipe(data?: Partial<TestRecipe>, phases?: TestRecipePhase[]): Promise<TestRecipe> {
    const plantId = await this.ensurePlantId();
    const payload = {
      name: data?.name || `Test Recipe ${Date.now()}`,
      description: data?.description || 'Test recipe description',
      plant_id: plantId,
      ...data,
    };

    const recipeResult = await this.postJsonWithRetry(`${baseURL}/api/recipes`, 'create recipe', payload, 5);
    const recipe = recipeResult.data;

    // Создаем ревизию рецепта (новая модель)
    const revisionResult = await this.postJsonWithRetry(
      `${baseURL}/api/recipes/${recipe.id}/revisions`,
      'create recipe revision',
      { description: 'Test revision' },
      5
    );
    const revision = revisionResult.data;

    // Создаем фазы ревизии, если они указаны
    if (phases && phases.length > 0) {
      for (const phase of phases) {
        const phasePayload: any = {
          phase_index: phase.phase_index,
          name: phase.name,
          duration_hours: phase.duration_hours,
        };

        // Преобразуем targets в новую структуру (колонки вместо JSON)
        if (phase.targets.ph !== undefined) {
          phasePayload.ph_target = phase.targets.ph;
          phasePayload.ph_min = phase.targets.ph - 0.2;
          phasePayload.ph_max = phase.targets.ph + 0.2;
        }
        if (phase.targets.ec !== undefined) {
          phasePayload.ec_target = phase.targets.ec;
          phasePayload.ec_min = phase.targets.ec - 0.2;
          phasePayload.ec_max = phase.targets.ec + 0.2;
        }
        if (phase.targets.temp_air !== undefined) {
          phasePayload.temp_air_target = phase.targets.temp_air;
        }
        if (phase.targets.humidity_air !== undefined) {
          phasePayload.humidity_target = phase.targets.humidity_air;
        }
        if (phase.targets.light_hours !== undefined) {
          phasePayload.lighting_photoperiod_hours = phase.targets.light_hours;
        }
        if (phase.targets.irrigation_interval_sec !== undefined) {
          phasePayload.irrigation_interval_sec = phase.targets.irrigation_interval_sec;
        }
        if (phase.targets.irrigation_duration_sec !== undefined) {
          phasePayload.irrigation_duration_sec = phase.targets.irrigation_duration_sec;
        }
        phasePayload.irrigation_mode = 'SUBSTRATE';

        await this.postWithRetry(
          `${baseURL}/api/recipe-revisions/${revision.id}/phases`,
          'create recipe revision phase',
          phasePayload,
          5
        );
      }

      // Публикуем ревизию после создания всех фаз
      await this.postWithRetry(
        `${baseURL}/api/recipe-revisions/${revision.id}/publish`,
        'publish recipe revision',
        undefined,
        5
      );
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

  async attachRecipeToZone(zoneId: number, recipeId: number, startAt?: string, plantId?: number): Promise<any> {
    // Новая модель: создаем grow-cycle вместо attach-recipe
    const headers = await this.getHeaders();
    const existingCycle = await this.getActiveCycle(zoneId, 5);
    if (existingCycle) {
      return existingCycle;
    }

    // Сначала получаем опубликованную ревизию рецепта
    const recipeResponse = await this.request.get(`${baseURL}/api/recipes/${recipeId}`, {
      headers,
    });

    if (!recipeResponse.ok()) {
      throw new Error(`Failed to get recipe: ${recipeResponse.status()} ${await recipeResponse.text()}`);
    }

    const recipeData = await recipeResponse.json();
    const recipe = recipeData.data;

    let publishedRevisionId = recipe.latest_published_revision_id || null;
    if (!publishedRevisionId && recipe.latestPublishedRevision?.id) {
      publishedRevisionId = recipe.latestPublishedRevision.id;
    }

    if (!publishedRevisionId && recipe.latest_draft_revision_id) {
      const publishResponse = await this.request.post(
        `${baseURL}/api/recipe-revisions/${recipe.latest_draft_revision_id}/publish`,
        { headers }
      );
      if (!publishResponse.ok()) {
        throw new Error(`Failed to publish draft revision: ${publishResponse.status()} ${await publishResponse.text()}`);
      }
      publishedRevisionId = recipe.latest_draft_revision_id;
    }

    if (!publishedRevisionId) {
      throw new Error(`Recipe ${recipeId} has no published revision`);
    }

    // Получаем или создаем plant (если не указан)
    let finalPlantId = plantId;
    if (!finalPlantId) {
      // Получаем первый доступный plant
      const plantsResponse = await this.request.get(`${baseURL}/api/plants`, {
        headers,
      });
      if (plantsResponse.ok()) {
        const plantsData = await plantsResponse.json();
        if (plantsData.data && plantsData.data.length > 0) {
          finalPlantId = plantsData.data[0].id;
        }
      }
      
      // Если нет растений, создаем тестовое
      if (!finalPlantId) {
        const createPlantResponse = await this.request.post(`${baseURL}/api/plants`, {
          headers,
          data: {
            name: `Test Plant ${Date.now()}`,
            scientific_name: 'Test Plant',
          },
        });
        if (createPlantResponse.ok()) {
          const plantData = await createPlantResponse.json();
          finalPlantId = plantData.data.id;
        }
      }
    }

    if (!finalPlantId) {
      throw new Error(`Failed to get or create plant for grow cycle`);
    }

    const payload: any = {
      recipe_revision_id: publishedRevisionId,
      plant_id: finalPlantId,
      start_immediately: !!startAt,
    };
    if (startAt) {
      payload.planting_at = startAt;
    }

    let lastError: Error | null = null;
    for (let attempt = 0; attempt < 5; attempt++) {
      const response = await this.request.post(`${baseURL}/api/zones/${zoneId}/grow-cycles`, {
        headers,
        data: payload,
      });

      if (response.ok()) {
        const result = await response.json();
        return result.data;
      }

      const status = response.status();
      const text = await response.text();
      let message = text;
      try {
        const parsed = JSON.parse(text);
        if (parsed?.message) {
          message = parsed.message;
        }
      } catch {
        // ignore JSON parse errors
      }

      if (status === 422 && typeof message === 'string' && message.toLowerCase().includes('active cycle')) {
        const activeCycle = await this.getActiveCycle(zoneId, 5);
        if (activeCycle) {
          return activeCycle;
        }
      }

      lastError = new Error(`Failed to create grow cycle: ${status} ${text}`);
      if (status !== 429) {
        throw lastError;
      }

      const retryAfterHeader = response.headers()['retry-after'];
      const retryAfter = retryAfterHeader ? Number(retryAfterHeader) : 0;
      const delay = Number.isFinite(retryAfter) && retryAfter > 0
        ? retryAfter * 1000
        : Math.min(2000 * Math.pow(2, attempt), 16000);
      await new Promise(resolve => setTimeout(resolve, delay));
    }

    throw lastError || new Error('Failed to create grow cycle after retries');
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

  async startZone(zoneId: number): Promise<void> {
    // Получаем активный цикл зоны
    const cycle = await this.getActiveCycle(zoneId, 2);

    if (!cycle || !cycle.id) {
      throw new Error(`Zone ${zoneId} has no active grow cycle`);
    }

    await this.postWithRetry(`${baseURL}/api/grow-cycles/${cycle.id}/start`, 'start cycle', undefined, 2);
  }

  async pauseZone(zoneId: number): Promise<void> {
    // Получаем активный цикл зоны
    const cycle = await this.getActiveCycle(zoneId, 2);

    if (!cycle || !cycle.id) {
      throw new Error(`Zone ${zoneId} has no active grow cycle`);
    }

    await this.postWithRetry(`${baseURL}/api/grow-cycles/${cycle.id}/pause`, 'pause cycle', undefined, 2);
  }

  async resumeZone(zoneId: number): Promise<void> {
    // Получаем активный цикл зоны
    const cycle = await this.getActiveCycle(zoneId, 2);

    if (!cycle || !cycle.id) {
      throw new Error(`Zone ${zoneId} has no active grow cycle`);
    }

    await this.postWithRetry(`${baseURL}/api/grow-cycles/${cycle.id}/resume`, 'resume cycle', undefined, 2);
  }

  async harvestZone(zoneId: number): Promise<void> {
    // Получаем активный цикл зоны
    const cycle = await this.getActiveCycle(zoneId, 2);

    if (!cycle || !cycle.id) {
      throw new Error(`Zone ${zoneId} has no active grow cycle`);
    }

    await this.postWithRetry(`${baseURL}/api/grow-cycles/${cycle.id}/harvest`, 'harvest cycle', {
      batch_label: `Test Batch ${Date.now()}`,
    }, 2);
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
