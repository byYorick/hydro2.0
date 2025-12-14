import { test as base, APIRequestContext } from '@playwright/test';
import { APITestHelper, TestGreenhouse, TestRecipe, TestZone, TestRecipePhase } from '../helpers/api';

type TestDataFixtures = {
  apiHelper: APITestHelper;
  testGreenhouse: TestGreenhouse;
  testRecipe: TestRecipe;
  testZone: TestZone;
};

export const test = base.extend<TestDataFixtures>({
  apiHelper: async ({ request, context }, use) => {
    // Получаем cookies из контекста браузера для использования в API запросах
    const cookies = await context.cookies();
    
    // Создаем helper с передачей cookies через функцию
    const helper = new APITestHelper(request, undefined, cookies);
    await use(helper);
  },

  testGreenhouse: async ({ apiHelper }, use) => {
    const greenhouse = await apiHelper.createTestGreenhouse();
    await use(greenhouse);
    // Очистка после теста
    await apiHelper.deleteGreenhouse(greenhouse.id).catch(() => {});
  },

  testRecipe: async ({ apiHelper }, use) => {
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
    const zone = await apiHelper.createTestZone(testGreenhouse.id);
    await use(zone);
    // Очистка после теста
    await apiHelper.deleteZone(zone.id).catch(() => {});
  },
});

export { expect } from '@playwright/test';

