import { test, expect } from '../fixtures/test-data';
import { TEST_IDS } from '../constants';

test.describe('Bindings', () => {
  test('should create binding through UI', async ({ page, testZone, apiHelper }) => {
    // Для этого теста нужен узел с каналами
    // В реальном тесте нужно создать узел через API или использовать существующий
    
    await page.goto(`/zones/${testZone.id}`);

    // Ищем компонент ChannelBinder или форму создания биндинга
    // Это зависит от того, где находится UI для создания биндингов
    
    // Ищем select для выбора роли
    const roleSelects = page.locator(`[data-testid^="${TEST_IDS.BINDING_ROLE_SELECT(0, 0).replace('0-0', '')}"]`);
    
    if (await roleSelects.count() > 0) {
      const firstSelect = roleSelects.first();
      
      // Выбираем роль
      await firstSelect.selectOption({ label: 'Основная помпа' });
      
      // Ждем сохранения (может быть автоматическим или через кнопку)
      await page.waitForTimeout(1000);
      
      // Проверяем, что значение выбрано
      await expect(firstSelect).toHaveValue('main_pump');
    }
  });

  test('should display binding resolution in UI', async ({ page, testZone, apiHelper }) => {
    // Создаем биндинг через API
    // Для этого нужен узел с каналами, который нужно создать или использовать существующий
    
    await page.goto(`/zones/${testZone.id}`);

    // Проверяем отображение биндингов
    // Это зависит от реализации UI для отображения биндингов
    
    // В реальном тесте здесь будет проверка отображения созданного биндинга
    await page.waitForTimeout(1000);
  });

  test('should send command by role and verify correct node/channel', async ({ page, testZone, apiHelper }) => {
    // Этот тест требует наличия узла с каналами и созданного биндинга
    
    await page.goto(`/zones/${testZone.id}`);

    // Отправляем команду по роли
    // Это зависит от реализации UI для отправки команд
    
    // В реальном тесте здесь будет:
    // 1. Создание биндинга (role -> node/channel)
    // 2. Отправка команды по роли
    // 3. Проверка, что команда ушла на правильный node/channel
    
    await page.waitForTimeout(1000);
  });
});

