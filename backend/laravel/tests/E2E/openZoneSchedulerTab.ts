import { expect, type Page } from '@playwright/test'

/**
 * Вкладка «Планировщик» у admin/agronomist лежит в меню «Ещё»,
 * у engineer — в основном tablist. Открываем тот пункт, который реально есть в layout роли.
 */
export async function openZoneSchedulerTab(page: Page): Promise<void> {
  const primaryTab = page.getByRole('tab', { name: 'Планировщик' })
  const moreTabs = page.getByTestId('zone-more-tabs')

  // Активный пункт из «Ещё» дублируется в tablist, поэтому оба локатора могут быть на странице.
  await expect(primaryTab.or(moreTabs).first()).toBeVisible()

  if ((await primaryTab.count()) > 0 && (await primaryTab.first().isVisible())) {
    await primaryTab.first().click()
    return
  }

  await moreTabs.click()
  await page.getByTestId('zone-more-tab-scheduler').click()
}
