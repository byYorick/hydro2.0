import { flushPromises, mount } from '@vue/test-utils'
import { reactive, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import RecipeEditor from '@/Components/RecipeEditor.vue'
import SubstrateCreateModal from '@/Components/SubstrateCreateModal.vue'
import { createDefaultRecipePhase, createRecipeEditorFormState } from '@/composables/recipeEditorShared'

const createPlant = vi.hoisted(() => vi.fn())
vi.mock('@/composables/useRole', () => ({ useRole: () => ({ isAdmin: ref(true) }) }))
vi.mock('@/composables/useToast', () => ({ useToast: () => ({ showToast: vi.fn() }) }))
vi.mock('@/services/api', () => ({ api: { plants: { create: createPlant } } }))

function editor() {
  const form = reactive(createRecipeEditorFormState(null))
  form.phases = [createDefaultRecipePhase(2), createDefaultRecipePhase(0)]
  const wrapper = mount(RecipeEditor, {
    props: { form, plants: [{ id: 1, name: 'Томат' }], npkProducts: [], calciumProducts: [], magnesiumProducts: [], microProducts: [] },
    global: { stubs: { RecipePhaseChartsPanel: true, RecipePhaseTimeline: true, RecipeSummaryStats: true } },
  })
  return { form, wrapper }
}

beforeEach(() => { createPlant.mockReset() })

describe('RecipeEditor component boundaries', () => {
  it('edits and removes the source phase when display order differs from array order', async () => {
    const { form, wrapper } = editor()
    await wrapper.get('[data-testid="phase-name-input-0"]').setValue('Ранняя фаза')
    expect(form.phases[1].name).toBe('Ранняя фаза')
    const remove = wrapper.get('[data-testid="phase-item-0"]').findAll('button').find(button => button.text() === 'Удалить')!
    await remove.trigger('click')
    expect(wrapper.emitted('remove-phase')).toEqual([[1]])
    wrapper.unmount()
  })

  it('keeps field edits in the shared draft across editor modes', async () => {
    const { form, wrapper } = editor()
    await wrapper.get('[data-testid="phase-item-0"] .target-row__input--main').setValue(6.2)
    expect(form.phases[1].ph_target).toBe(6.2)
    await wrapper.get('[data-testid="recipe-editor-mode-simple"]').trigger('click')
    await wrapper.get('[data-testid="recipe-editor-mode-advanced"]').trigger('click')
    expect(form.phases[1].ph_target).toBe(6.2)
    expect(wrapper.get('[data-testid="phase-item-0"] .target-row__input--main').element).toHaveProperty('value', '6.2')
    wrapper.unmount()
  })

  it('forwards substrate creation through phase fields to the shared modal and form', async () => {
    const { form, wrapper } = editor()
    await wrapper.get('[data-testid="phase-item-0"] button[title="Создать новый субстрат"]').trigger('click')
    const modal = wrapper.findComponent(SubstrateCreateModal)
    expect(modal.props('open')).toBe(true)
    const substrate = { id: 3, code: 'new-soil', name: 'Новый субстрат', applicable_systems: ['drip_tape', 'drip_emitter'] }
    modal.vm.$emit('created', substrate)
    await flushPromises()
    expect(wrapper.emitted('substrate-created')).toEqual([[substrate]])
    expect(form.phases.every(phase => phase.substrate_type === 'new-soil')).toBe(true)
    expect(modal.props('open')).toBe(false)
    wrapper.unmount()
  })

  it('selects a newly created plant and forwards its identity to the owner', async () => {
    createPlant.mockResolvedValue({ id: 8, name: 'Базилик' })
    const { form, wrapper } = editor()
    const create = wrapper.findAll('button').find(button => button.text() === 'Создать')!
    await create.trigger('click')
    await wrapper.get('input[placeholder="Томат Черри"]').setValue('Базилик')
    await wrapper.findAll('button').find(button => button.text() === 'Создать растение')!.trigger('click')
    await flushPromises()
    expect(form.plant_id).toBe(8)
    expect(wrapper.emitted('plant-created')).toEqual([[{ id: 8, name: 'Базилик' }]])
    expect(createPlant).toHaveBeenCalledWith({ name: 'Базилик', species: null, variety: null })
    wrapper.unmount()
  })
})
