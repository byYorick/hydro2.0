import { test as base, request as playwrightRequest } from '@playwright/test';
import { APITestHelper, TestGreenhouse, TestRecipe, TestZone, TestRecipePhase } from '../helpers/api';

type TestDataFixtures = {
  apiHelper: APITestHelper;
  testGreenhouse: TestGreenhouse;
  testRecipe: TestRecipe;
  testZone: TestZone;
};

export const test = base.extend<TestDataFixtures>({
  apiHelper: async ({ context }, use) => {
    // Получаем storageState из контекста браузера
    const storageState = await context.storageState();
    
    // Создаем новый APIRequestContext с storageState для передачи cookies
    const apiRequest = await playwrightRequest.newContext({
      storageState: storageState,
    });
    
    const helper = new APITestHelper(apiRequest);
    await use(helper);
    
    // Закрываем request context после использования
    await apiRequest.dispose();
  },

  testGreenhouse: async ({ apiHelper }, use) => {
    // Добавляем задержку для избежания rate limiting
    await new Promise(resolve => setTimeout(resolve, 1000));
    const greenhouse = await apiHelper.createTestGreenhouse();
    await use(greenhouse);
    // Очистка после теста
    await apiHelper.deleteGreenhouse(greenhouse.id).catch(() => {});
  },

  testRecipe: async ({ apiHelper }, use) => {
    // Добавляем задержку для избежания rate limiting
    await new Promise(resolve => setTimeout(resolve, 500));
    const phases: TestRecipePhase[] = [
      {
        phase_index: 0,
        name: 'Seedling',
        duration_hours: 168,
        targets: {
          ph: 5.8,
          ec: 1.2,
          temp_air: 22,
          humidity_air: 65,
          light_hours: 18,
          irrigation_interval_sec: 900,
          irrigation_duration_sec: 10,
        },
      },
      {
        phase_index: 1,
        name: 'Vegetative',
        duration_hours: 336,
        targets: {
          ph: 5.8,
          ec: 1.4,
          temp_air: 23,
          humidity_air: 60,
          light_hours: 16,
          irrigation_interval_sec: 720,
          irrigation_duration_sec: 12,
        },
      },
    ];
    const recipe = await apiHelper.createTestRecipe(undefined, phases);
    await use(recipe);
    // Очистка после теста
    await apiHelper.deleteRecipe(recipe.id).catch(() => {});
  },

  testZone: async ({ apiHelper, testGreenhouse }, use) => {
    // Добавляем задержку для избежания rate limiting
    await new Promise(resolve => setTimeout(resolve, 500));
    const zone = await apiHelper.createTestZone(testGreenhouse.id);
    await use(zone);
    // Очистка после теста
    await apiHelper.deleteZone(zone.id).catch(() => {});
  },
});

export { expect } from '@playwright/test';

