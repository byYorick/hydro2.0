await page.getByLabel("Узел коррекции pH").selectOption(["7"]);
await page.getByLabel("Узел коррекции pH").evaluate((el) => {
  const container = el.closest("div.grid.grid-cols-1.gap-2.items-end");
  const btn = container?.querySelector("button");
  if (!btn) throw new Error("pH bind button not found");
  btn.click();
});

await page.getByLabel("Узел коррекции EC").selectOption(["9"]);
await page.getByLabel("Узел коррекции EC").evaluate((el) => {
  const container = el.closest("div.grid.grid-cols-1.gap-2.items-end");
  const btn = container?.querySelector("button");
  if (!btn) throw new Error("EC bind button not found");
  btn.click();
});
