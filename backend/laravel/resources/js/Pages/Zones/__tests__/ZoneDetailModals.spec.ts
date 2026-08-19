import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import ZoneDetailModals from '../ZoneDetailModals.vue'

vi.mock('@/Components/ZoneActionModal.vue', () => ({
  default: { name: 'ZoneActionModal', template: '<div />' },
}))
vi.mock('@/Components/PumpCalibrationModal.vue', () => ({
  default: { name: 'PumpCalibrationModal', template: '<div />' },
}))
vi.mock('@/Components/AttachNodesModal.vue', () => ({
  default: { name: 'AttachNodesModal', template: '<div />' },
}))
vi.mock('@/Components/NodeConfigModal.vue', () => ({
  default: { name: 'NodeConfigModal', template: '<div />' },
}))
vi.mock('@/Components/ConfirmModal.vue', () => ({
  default: {
    name: 'ConfirmModal',
    props: ['open', 'title'],
    template: '<div v-if="open"><slot /></div>',
  },
}))

const baseProps = {
  zoneId: 12,
  zoneName: 'Zone A',
  devices: [],
  currentPhaseTargets: null,
  activeCycle: { id: 77 },
  selectedNodeId: null,
  selectedNode: null,
  currentActionType: 'START_IRRIGATION' as const,
  showActionModal: false,
  showPumpCalibrationModal: false,
  showAttachNodesModal: false,
  showNodeConfigModal: false,
  harvestModal: { open: true, batchLabel: '', yieldKg: '' },
  abortModal: { open: false, notes: '' },
  changeRecipeModal: { open: false, recipeRevisionId: '', applyMode: 'now' as const },
  loading: {
    actionSubmit: false,
    cycleHarvest: false,
    cycleAbort: false,
    cycleChangeRecipe: false,
    pumpCalibrationRun: false,
    pumpCalibrationSave: false,
  },
  pumpCalibrationSaveSeq: 0,
  pumpCalibrationRunSeq: 0,
  pumpCalibrationLastRunToken: null,
}

describe('ZoneDetailModals', () => {
  it('в модалке сбора есть опциональное поле урожая в кг', () => {
    const wrapper = mount(ZoneDetailModals, { props: baseProps })
    const input = wrapper.get('[data-testid="harvest-yield-kg"]')

    expect(wrapper.text()).toContain('Урожай, кг')
    expect(input.attributes('placeholder')).toBe('Необязательно')
  })

  it('confirm без кг остаётся доступным', async () => {
    const wrapper = mount(ZoneDetailModals, { props: baseProps })
    const input = wrapper.get('[data-testid="harvest-yield-kg"]')

    expect((input.element as HTMLInputElement).value).toBe('')
    await wrapper.getComponent({ name: 'ConfirmModal' }).vm.$emit('confirm')
    expect(wrapper.emitted('confirm-harvest')).toHaveLength(1)
  })
})
