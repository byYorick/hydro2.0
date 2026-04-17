import { execFileSync } from 'node:child_process';
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

function buildCanonicalTestRecipePhasePayload(phase: TestRecipePhase): Record<string, any> {
  const phTarget = phase.targets.ph ?? null
  const ecTarget = phase.targets.ec ?? null
  const tempAirTarget = phase.targets.temp_air ?? null
  const humidityTarget = phase.targets.humidity_air ?? null
  const lightHours = phase.targets.light_hours ?? null
  const irrigationInterval = phase.targets.irrigation_interval_sec ?? null
  const irrigationDuration = phase.targets.irrigation_duration_sec ?? null

  return {
    phase_index: phase.phase_index,
    name: phase.name,
    duration_hours: phase.duration_hours,
    ph_target: phTarget,
    ph_min: phTarget !== null ? phTarget - 0.2 : null,
    ph_max: phTarget !== null ? phTarget + 0.2 : null,
    ec_target: ecTarget,
    ec_min: ecTarget !== null ? ecTarget - 0.2 : null,
    ec_max: ecTarget !== null ? ecTarget + 0.2 : null,
    temp_air_target: tempAirTarget,
    humidity_target: humidityTarget,
    lighting_photoperiod_hours: lightHours,
    lighting_start_time: '06:00:00',
    irrigation_mode: 'SUBSTRATE',
    irrigation_interval_sec: irrigationInterval,
    irrigation_duration_sec: irrigationDuration,
    extensions: {
      day_night: {
        ph: { day: phTarget, night: phTarget },
        ec: { day: ecTarget, night: ecTarget },
        temperature: { day: tempAirTarget, night: tempAirTarget },
        humidity: { day: humidityTarget, night: humidityTarget },
        lighting: { day_start_time: '06:00:00', day_hours: lightHours },
      },
      subsystems: {
        irrigation: {
          targets: {
            system_type: 'drip',
          },
        },
      },
    },
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

export interface SeededGreenhouseClimateNodes {
  climateSensor: {
    id: number;
    uid: string;
    name: string;
  };
  ventActuator: {
    id: number;
    uid: string;
    name: string;
  };
  uids: string[];
}

export interface ZoneLiveEditState {
  id: number;
  control_mode: string;
  config_mode: string;
  live_until: string | null;
}

export class APITestHelper {
  constructor(
    private request: APIRequestContext, 
    private token?: string
  ) {}

  static bootstrapToken(email: string, role: string): string {
    const output = execFileSync(
      'php',
      ['artisan', 'e2e:auth-bootstrap', `--email=${email}`, `--role=${role}`],
      {
        cwd: process.cwd(),
        encoding: 'utf8',
      },
    );

    const token = output
      .trim()
      .split(/\r?\n/)
      .map((line) => line.trim())
      .reverse()
      .find((line) => line.includes('|'));

    if (!token) {
      throw new Error(`Failed to bootstrap E2E auth token: ${output}`);
    }

    return token;
  }

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

  private runArtisanTinkerJson<T>(code: string): T {
    const output = execFileSync('php', ['artisan', 'tinker', `--execute=${code}`], {
      cwd: process.cwd(),
      encoding: 'utf8',
    });
    const jsonLine = output
      .trim()
      .split(/\r?\n/)
      .map((line) => line.trim())
      .reverse()
      .find((line) => line.startsWith('{') || line.startsWith('['));

    if (!jsonLine) {
      throw new Error(`Failed to parse artisan tinker output as JSON: ${output}`);
    }

    return JSON.parse(jsonLine) as T;
  }

  async seedGreenhouseClimateNodes(prefix = `e2e-gh-${Date.now()}`): Promise<SeededGreenhouseClimateNodes> {
    const safePrefix = prefix.replace(/[^a-zA-Z0-9_-]/g, '-');

    return this.runArtisanTinkerJson<SeededGreenhouseClimateNodes>(`
      $prefix = '${safePrefix}';
      $climate = \\App\\Models\\DeviceNode::query()->create([
        'uid' => $prefix . '-climate-sensor',
        'name' => 'E2E Climate Sensor ' . $prefix,
        'type' => 'climate',
        'status' => 'online',
      ]);
      \\App\\Models\\NodeChannel::query()->create([
        'node_id' => $climate->id,
        'channel' => 'temp_air',
        'type' => 'SENSOR',
      ]);
      \\App\\Models\\NodeChannel::query()->create([
        'node_id' => $climate->id,
        'channel' => 'humidity_air',
        'type' => 'SENSOR',
      ]);
      $vent = \\App\\Models\\DeviceNode::query()->create([
        'uid' => $prefix . '-vent-actuator',
        'name' => 'E2E Vent Actuator ' . $prefix,
        'type' => 'climate',
        'status' => 'online',
      ]);
      \\App\\Models\\NodeChannel::query()->create([
        'node_id' => $vent->id,
        'channel' => 'vent_drive',
        'type' => 'ACTUATOR',
      ]);
      \\App\\Models\\NodeChannel::query()->create([
        'node_id' => $vent->id,
        'channel' => 'vent_window_pct',
        'type' => 'ACTUATOR',
      ]);
      echo json_encode([
        'climateSensor' => [
          'id' => $climate->id,
          'uid' => $climate->uid,
          'name' => $climate->name,
        ],
        'ventActuator' => [
          'id' => $vent->id,
          'uid' => $vent->uid,
          'name' => $vent->name,
        ],
        'uids' => [$climate->uid, $vent->uid],
      ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    `);
  }

  async cleanupNodesByUids(uids: string[]): Promise<void> {
    const safeUids = uids
      .map((uid) => String(uid).trim())
      .filter((uid) => uid.length > 0)
      .map((uid) => `'${uid.replace(/'/g, "\\'")}'`);

    if (safeUids.length === 0) {
      return;
    }

    this.runArtisanTinkerJson<{ deleted: number }>(`
      $uids = [${safeUids.join(', ')}];
      $deleted = \\App\\Models\\DeviceNode::query()->whereIn('uid', $uids)->delete();
      echo json_encode(['deleted' => $deleted], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    `);
  }

  async primeZoneForLiveEdit(zoneId: number, liveUntilIso: string): Promise<ZoneLiveEditState> {
    return this.runArtisanTinkerJson<ZoneLiveEditState>(`
      $zone = \\App\\Models\\Zone::query()->findOrFail(${zoneId});
      $zone->control_mode = 'manual';
      $zone->config_mode = 'live';
      $zone->live_started_at = now();
      $zone->live_until = '${liveUntilIso}';
      $zone->save();
      echo json_encode([
        'id' => $zone->id,
        'control_mode' => $zone->control_mode,
        'config_mode' => $zone->config_mode,
        'live_until' => optional($zone->live_until)->toISOString(),
      ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    `);
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
        await this.postWithRetry(
          `${baseURL}/api/recipe-revisions/${revision.id}/phases`,
          'create recipe revision phase',
          buildCanonicalTestRecipePhasePayload(phase),
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
    const uniqueSuffix = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const payload = {
      greenhouse_id: greenhouseId,
      name: data?.name || `Test Zone ${uniqueSuffix}`,
      description: data?.description || 'Test zone description',
      status: data?.status || 'PLANNED',
      uid: (data as any)?.uid || `zn-test-zone-${uniqueSuffix}`,
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

  async createBinding(
    infrastructureInstanceId: number,
    nodeChannelId: number,
    role: string,
    direction: 'actuator' | 'sensor' = 'actuator',
  ): Promise<void> {
    const response = await this.request.post(`${baseURL}/api/channel-bindings`, {
      headers: await this.getHeaders(),
      data: {
        infrastructure_instance_id: infrastructureInstanceId,
        node_channel_id: nodeChannelId,
        direction,
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

  async setZoneControlMode(
    zoneId: number,
    controlMode: 'auto' | 'semi' | 'manual',
    reason = 'playwright control mode setup'
  ): Promise<any> {
    const headers = await this.getHeaders();
    const response = await this.request.post(`${baseURL}/api/zones/${zoneId}/control-mode`, {
      headers,
      data: {
        control_mode: controlMode,
        source: 'playwright',
        reason,
      },
    });

    if (!response.ok()) {
      throw new Error(`Failed to set control mode for zone ${zoneId}: ${response.status()} ${await response.text()}`);
    }

    return response.json();
  }

  async setZoneConfigMode(
    zoneId: number,
    payload: {
      mode: 'locked' | 'live';
      reason: string;
      live_until?: string | null;
    }
  ): Promise<any> {
    const headers = await this.getHeaders();
    const response = await this.request.patch(`${baseURL}/api/zones/${zoneId}/config-mode`, {
      headers,
      data: payload,
    });

    if (!response.ok()) {
      throw new Error(`Failed to set config mode for zone ${zoneId}: ${response.status()} ${await response.text()}`);
    }

    return response.json();
  }

  async applyCorrectionLiveEdit(
    zoneId: number,
    payload: {
      reason: string;
      phase?: 'generic' | 'solution_fill' | 'tank_recirc' | 'irrigation';
      correction_patch?: Record<string, unknown>;
      calibration_patch?: Record<string, unknown>;
    }
  ): Promise<any> {
    const headers = await this.getHeaders();
    const response = await this.request.put(`${baseURL}/api/zones/${zoneId}/correction/live-edit`, {
      headers,
      data: payload,
    });

    if (!response.ok()) {
      throw new Error(`Failed to apply correction live edit for zone ${zoneId}: ${response.status()} ${await response.text()}`);
    }

    return response.json();
  }

  async getAutomationConfig(scopeType: 'system' | 'greenhouse' | 'zone' | 'grow_cycle', scopeId: number, namespace: string): Promise<any> {
    const response = await this.request.get(`${baseURL}/api/automation-configs/${scopeType}/${scopeId}/${namespace}`, {
      headers: await this.getHeaders(),
    });

    if (!response.ok()) {
      throw new Error(`Failed to get automation config ${namespace}: ${response.status()} ${await response.text()}`);
    }

    const result = await response.json();
    return result.data;
  }

  async updateAutomationConfig(
    scopeType: 'system' | 'greenhouse' | 'zone' | 'grow_cycle',
    scopeId: number,
    namespace: string,
    payload: Record<string, any>
  ): Promise<any> {
    const response = await this.request.put(`${baseURL}/api/automation-configs/${scopeType}/${scopeId}/${namespace}`, {
      headers: await this.getHeaders(),
      data: { payload },
    });

    if (!response.ok()) {
      throw new Error(`Failed to update automation config ${namespace}: ${response.status()} ${await response.text()}`);
    }

    const result = await response.json();
    return result.data;
  }

  async resetAutomationConfig(scopeType: 'system' | 'greenhouse' | 'zone' | 'grow_cycle', scopeId: number, namespace: string): Promise<any> {
    const response = await this.request.delete(`${baseURL}/api/automation-configs/${scopeType}/${scopeId}/${namespace}`, {
      headers: await this.getHeaders(),
    });

    if (!response.ok()) {
      throw new Error(`Failed to reset automation config ${namespace}: ${response.status()} ${await response.text()}`);
    }

    const result = await response.json();
    return result.data;
  }

  async getAutomationBundle(scopeType: 'system' | 'zone' | 'grow_cycle', scopeId: number): Promise<any> {
    const response = await this.request.get(`${baseURL}/api/automation-bundles/${scopeType}/${scopeId}`, {
      headers: await this.getHeaders(),
    });

    if (!response.ok()) {
      throw new Error(`Failed to get automation bundle ${scopeType}/${scopeId}: ${response.status()} ${await response.text()}`);
    }

    const result = await response.json();
    return result.data;
  }

  async validateAutomationBundle(scopeType: 'system' | 'zone' | 'grow_cycle', scopeId: number): Promise<any> {
    const response = await this.request.post(`${baseURL}/api/automation-bundles/${scopeType}/${scopeId}/validate`, {
      headers: await this.getHeaders(),
    });

    if (!response.ok()) {
      throw new Error(`Failed to validate automation bundle ${scopeType}/${scopeId}: ${response.status()} ${await response.text()}`);
    }

    const result = await response.json();
    return result.data;
  }

  async listAutomationPresets(namespace: string): Promise<any[]> {
    const response = await this.request.get(`${baseURL}/api/automation-presets/${namespace}`, {
      headers: await this.getHeaders(),
    });

    if (!response.ok()) {
      throw new Error(`Failed to list automation presets ${namespace}: ${response.status()} ${await response.text()}`);
    }

    const result = await response.json();
    return Array.isArray(result.data) ? result.data : [];
  }

  async createAutomationPreset(namespace: string, payload: { name: string; description?: string | null; payload: Record<string, any> }): Promise<any> {
    const response = await this.request.post(`${baseURL}/api/automation-presets/${namespace}`, {
      headers: await this.getHeaders(),
      data: payload,
    });

    if (!response.ok()) {
      throw new Error(`Failed to create automation preset ${namespace}: ${response.status()} ${await response.text()}`);
    }

    const result = await response.json();
    return result.data;
  }

  async deleteAutomationPreset(presetId: number): Promise<void> {
    const response = await this.request.delete(`${baseURL}/api/automation-presets/${presetId}`, {
      headers: await this.getHeaders(),
    });

    if (!response.ok()) {
      throw new Error(`Failed to delete automation preset ${presetId}: ${response.status()} ${await response.text()}`);
    }
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
