import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

describe('RecipeEditor ae4 wave1 fields', () => {
  it('поля полива волны 1 в той же форме, без нового меню', () => {
    const source = readFileSync(
      resolve(__dirname, '../RecipeEditor.vue'),
      'utf8',
    )
    expect(source).toContain('data-testid="phase-soil-moisture-min"')
    expect(source).toContain('data-testid="phase-vpd-min"')
    expect(source).toContain('data-testid="phase-light-integral-per-shot"')
    expect(source).not.toMatch(/AE4|ae4 menu|новое меню/i)
    expect(source).toContain('Интервал между поливами')
  })
})
