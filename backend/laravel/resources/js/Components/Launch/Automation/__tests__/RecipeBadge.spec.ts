import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import RecipeBadge from '../RecipeBadge.vue'

describe('RecipeBadge', () => {
  it('renders recipe name + revision', () => {
    const w = mount(RecipeBadge, {
      props: {
        recipeName: 'Tomato NFT',
        revisionLabel: 'r3',
        systemType: 'nft',
        targetPh: 5.8,
        targetEc: 1.6,
      },
    })
    expect(w.text()).toContain('Tomato NFT')
    expect(w.text()).toContain('r3')
    expect(w.text()).toContain('nft')
    expect(w.text()).toContain('5.8')
    expect(w.text()).toContain('1.6')
  })

  it('omits parts that are not provided', () => {
    const w = mount(RecipeBadge, {
      props: { systemType: 'drip' },
    })
    expect(w.text()).toContain('drip')
    expect(w.text()).not.toMatch(/targetPh = 5/)
    expect(w.text()).not.toMatch(/targetEc = /)
  })

  it('always shows the lock-warning text', () => {
    const w = mount(RecipeBadge, { props: {} })
    expect(w.text()).toContain('только в шаге «Рецепт»')
  })
})
