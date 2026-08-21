import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

const apiGetMock = vi.hoisted(() => vi.fn())
const apiPatchMock = vi.hoisted(() => vi.fn())
const apiPostMock = vi.hoisted(() => vi.fn())
const apiDeleteMock = vi.hoisted(() => vi.fn())
const getDocumentMock = vi.hoisted(() => vi.fn())
const updateDocumentMock = vi.hoisted(() => vi.fn())
const resetDocumentMock = vi.hoisted(() => vi.fn())
const showToastMock = vi.hoisted(() => vi.fn())

vi.mock('@/Layouts/AppLayout.vue', () => ({
  default: { name: 'AppLayout', template: '<div><slot /></div>' },
}))

vi.mock('@/Components/Card.vue', () => ({
  default: { name: 'Card', template: '<div><slot /></div>' },
}))

vi.mock('@/Components/Button.vue', () => ({
  default: {
    name: 'Button',
    props: ['disabled', 'variant', 'size', 'type'],
    emits: ['click'],
    template: '<button :disabled="disabled" :type="type" @click="$emit(\'click\')"><slot /></button>',
  },
}))

vi.mock('@/Components/Badge.vue', () => ({
  default: { name: 'Badge', props: ['variant'], template: '<span><slot /></span>' },
}))

vi.mock('@/Components/Modal.vue', () => ({
  default: {
    name: 'Modal',
    props: ['open', 'title'],
    emits: ['close'],
    template: '<div v-if="open"><slot /><slot name="footer" /></div>',
  },
}))

vi.mock('@/Components/Pagination.vue', () => ({
  default: {
    name: 'Pagination',
    props: ['currentPage', 'perPage', 'total'],
    emits: ['update:current-page', 'update:per-page'],
    template: '<div data-test="pagination" />',
  },
}))

vi.mock('@/utils/i18n', () => ({
  translateRole: (role: string | undefined) => role ?? 'unknown',
}))

vi.mock('@/utils/logger', () => ({
  logger: {
    error: vi.fn(),
  },
}))

vi.mock('@/composables/useApi', () => ({
  useApi: () => ({
    api: {
      get: (url: string) => apiGetMock(url),
      patch: (url: string, payload?: unknown) => apiPatchMock(url, payload),
      post: (url: string, payload?: unknown) => apiPostMock(url, payload),
      delete: (url: string) => apiDeleteMock(url),
    },
  }),
}))

vi.mock('@/composables/useAutomationConfig', () => ({
  useAutomationConfig: () => ({
    getDocument: getDocumentMock,
    updateDocument: updateDocumentMock,
    resetDocument: resetDocumentMock,
    loading: ref(false),
  }),
}))

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({
    showToast: showToastMock,
  }),
}))

vi.mock('@/composables/useModal', () => ({
  useSimpleModal: () => ({
    isOpen: ref(false),
    open: vi.fn(),
    close: vi.fn(),
  }),
}))

const pageUser = vi.hoisted(() => ({
  id: 7,
  role: 'admin',
  name: 'Admin',
  email: 'admin@example.com',
  preferences: {
    alert_toast_suppression_sec: 25,
  },
}))

vi.mock('@/Pages/Profile/Partials/UpdatePasswordForm.vue', () => ({
  default: {
    name: 'UpdatePasswordForm',
    template: '<section data-testid="settings-update-password"><h2>Изменение пароля</h2></section>',
  },
}))

vi.mock('@inertiajs/vue3', () => ({
  Link: {
    name: 'Link',
    props: ['href'],
    template: '<a :href="href"><slot /></a>',
  },
  usePage: () => ({
    props: {
      auth: {
        user: pageUser,
      },
      users: [],
      automationEngineSettings: {
        snapshot: {
          sections: [
            {
              key: 'legacy',
              title: 'Legacy props snapshot',
              items: [
                {
                  key: 'legacy.scheduler_due_grace_sec',
                  label: 'Legacy prop item',
                  value: 999,
                },
              ],
            },
          ],
        },
      },
    },
  }),
}))

import SettingsIndex from '../Index.vue'

function makeRuntimeDocument(value = 15) {
  return {
    namespace: 'system.runtime',
    scope_type: 'system',
    scope_id: 0,
    schema_version: 1,
    payload: {
      'automation_engine.scheduler_due_grace_sec': value,
    },
    snapshot: {
      generated_at: '2026-03-24T11:00:00Z',
      sections: [
        {
          key: 'scheduler',
          title: 'Scheduler',
          items: [
            {
              key: 'automation_engine.scheduler_due_grace_sec',
              label: 'Due grace',
              value,
              type: 'int',
              editable: true,
              input_type: 'number',
              step: 1,
              min: 1,
              max: 600,
              source: value === 15 ? 'default' : 'override',
              description: 'Grace period for due tasks.',
            },
          ],
        },
      ],
    },
    status: 'valid',
    updated_at: '2026-03-24T11:00:00Z',
    updated_by: 1,
  }
}

function makeAlertPoliciesDocument(value = 'manual_ack') {
  return {
    namespace: 'system.alert_policies',
    scope_type: 'system',
    scope_id: 0,
    schema_version: 1,
    payload: {
      ae3_operational_resolution_mode: value,
    },
    status: 'valid',
    updated_at: '2026-03-24T11:00:00Z',
    updated_by: 1,
  }
}

function mountSettings(role = 'admin') {
  pageUser.role = role
  pageUser.name = role.charAt(0).toUpperCase() + role.slice(1)
  pageUser.email = `${role}@example.com`
  return mount(SettingsIndex)
}

function tabLabels(wrapper: ReturnType<typeof mount>) {
  return wrapper.findAll('[role="tab"]').map((tab) => tab.text())
}

describe('Settings/Index.vue', () => {
  beforeEach(() => {
    pageUser.id = 7
    pageUser.role = 'admin'
    pageUser.name = 'Admin'
    pageUser.email = 'admin@example.com'
    pageUser.preferences = {
      alert_toast_suppression_sec: 25,
    }
    apiGetMock.mockReset()
    apiPatchMock.mockReset()
    apiPostMock.mockReset()
    apiDeleteMock.mockReset()
    getDocumentMock.mockReset()
    updateDocumentMock.mockReset()
    resetDocumentMock.mockReset()
    showToastMock.mockReset()

    apiGetMock.mockImplementation((url: string) => {
      if (url === '/settings/preferences') {
        return Promise.resolve({
          data: {
            data: {
              alert_toast_suppression_sec: 25,
            },
          },
        })
      }

      return Promise.resolve({ data: { data: [] } })
    })
    updateDocumentMock.mockImplementation(async (_scopeType: string, _scopeId: number, namespace: string, payload?: Record<string, unknown>) => {
      if (namespace === 'system.alert_policies') {
        return makeAlertPoliciesDocument(String(payload?.ae3_operational_resolution_mode || 'manual_ack'))
      }
      return makeRuntimeDocument(Number(payload?.['automation_engine.scheduler_due_grace_sec'] || 45))
    })
    resetDocumentMock.mockImplementation(async (_scopeType: string, _scopeId: number, namespace: string) => {
      if (namespace === 'system.alert_policies') {
        return makeAlertPoliciesDocument('manual_ack')
      }
      return makeRuntimeDocument(15)
    })
    getDocumentMock.mockImplementation(async (_scopeType: string, _scopeId: number, namespace: string) => {
      if (namespace === 'system.alert_policies') {
        return makeAlertPoliciesDocument()
      }
      return makeRuntimeDocument()
    })
  })

  it('читает runtime snapshot только через authority API и игнорирует legacy page props', async () => {
    const wrapper = mountSettings('admin')

    await flushPromises()

    expect(getDocumentMock).toHaveBeenCalledWith('system', 0, 'system.runtime')
    expect(getDocumentMock).toHaveBeenCalledWith('system', 0, 'system.alert_policies')
    expect(wrapper.text()).toContain('Планировщик задач')
    expect(wrapper.text()).toContain('Закрытие тревог автоматики')
    expect(wrapper.text()).toContain('Scheduler')
    expect(wrapper.text()).toContain('Due grace')
    expect(wrapper.text()).not.toContain('Legacy props snapshot')
    expect(wrapper.text()).not.toContain('Legacy prop item')
  })

  it('после mount открывает секцию Профиль, а не Автоматика', async () => {
    const wrapper = mountSettings('admin')

    await flushPromises()

      expect(wrapper.find('[role="tab"][aria-selected="true"]').text()).toBe('Мой профиль')
    expect(wrapper.get('[data-testid="settings-section-profile"]').isVisible()).toBe(true)
    expect(wrapper.get('[data-testid="settings-automation-engine-card"]').isVisible()).toBe(false)
  })

  it.each(['operator', 'agronomist'] as const)(
    'не показывает секцию Автоматика, AE3 alerts и reset для роли %s',
    async (role) => {
      const wrapper = mountSettings(role)

      await flushPromises()

      expect(tabLabels(wrapper)).not.toContain('Параметры движка')
      expect(tabLabels(wrapper)).not.toContain('Настройки системы')
      expect(wrapper.find('[data-testid="settings-automation-engine-card"]').exists()).toBe(false)
      expect(wrapper.find('[data-testid="settings-alert-policies-card"]').exists()).toBe(false)
      expect(wrapper.find('[data-testid="settings-system-authority-card"]').exists()).toBe(false)
      expect(wrapper.find('[data-testid="settings-automation-engine-reset"]').exists()).toBe(false)
      expect(wrapper.find('[data-testid="settings-alert-policy-reset"]').exists()).toBe(false)
      expect(wrapper.text()).not.toContain('Закрытие тревог')
      expect(getDocumentMock).not.toHaveBeenCalled()
    },
  )

  it.each(['admin', 'engineer'] as const)(
    'показывает секцию Автоматика для роли %s, но не делает её стартовой',
    async (role) => {
      const wrapper = mountSettings(role)

      await flushPromises()

      expect(tabLabels(wrapper)).toContain('Параметры движка')
      expect(wrapper.find('[data-testid="settings-automation-engine-card"]').exists()).toBe(true)
      expect(wrapper.find('[data-testid="settings-alert-policies-card"]').exists()).toBe(true)
      expect(wrapper.find('[data-testid="settings-automation-engine-reset"]').exists()).toBe(true)
      expect(wrapper.text()).toContain('Закрытие тревог')
      expect(wrapper.find('[role="tab"][aria-selected="true"]').text()).toBe('Мой профиль')
      expect(getDocumentMock).toHaveBeenCalledWith('system', 0, 'system.runtime')
      expect(getDocumentMock).toHaveBeenCalledWith('system', 0, 'system.alert_policies')
    },
  )

  it('admin видит вкладку «Настройки системы», старт остаётся «Мой профиль»', async () => {
    const wrapper = mountSettings('admin')

    await flushPromises()

    expect(tabLabels(wrapper)).toContain('Настройки системы')
    expect(wrapper.find('[data-testid="settings-system-authority-card"]').exists()).toBe(true)
    expect(wrapper.find('[role="tab"][aria-selected="true"]').text()).toBe('Мой профиль')
    expect(wrapper.get('[data-testid="settings-section-profile"]').isVisible()).toBe(true)
    expect(wrapper.get('[data-testid="settings-system-authority-card"]').isVisible()).toBe(false)
    expect(wrapper.get('[data-testid="settings-theme-toggle"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="settings-update-password"]').exists()).toBe(true)
  })

  it('engineer не видит вкладку «Настройки системы»', async () => {
    const wrapper = mountSettings('engineer')

    await flushPromises()

    expect(tabLabels(wrapper)).toContain('Параметры движка')
    expect(tabLabels(wrapper)).not.toContain('Настройки системы')
    expect(wrapper.find('[data-testid="settings-system-authority-card"]').exists()).toBe(false)
    expect(wrapper.find('[role="tab"][aria-selected="true"]').text()).toBe('Мой профиль')
  })

  it('сохраняет и сбрасывает runtime overrides через authority document endpoints', async () => {
    const wrapper = mountSettings('admin')

    await flushPromises()

    await wrapper.get('[data-testid="settings-automation-engine-input-automation_engine.scheduler_due_grace_sec"]').setValue('45')
    await wrapper.get('[data-testid="settings-automation-engine-save"]').trigger('click')
    await flushPromises()

    expect(updateDocumentMock).toHaveBeenCalledWith(
      'system',
      0,
      'system.runtime',
      {
        'automation_engine.scheduler_due_grace_sec': 45,
      },
    )

    await wrapper.get('[data-testid="settings-automation-engine-reset"]').trigger('click')
    await flushPromises()
    const confirmButtons = wrapper.findAll('button').filter((button) => button.text() === 'Сбросить')
    await confirmButtons[confirmButtons.length - 1]?.trigger('click')
    await flushPromises()

    expect(resetDocumentMock).toHaveBeenCalledWith('system', 0, 'system.runtime')
  })

  it('сохраняет alert policy через authority document endpoints', async () => {
    const wrapper = mountSettings('admin')

    await flushPromises()

    await wrapper.get('[data-testid="settings-alert-policy-input-ae3-operational-resolution-mode"]').setValue('auto_resolve_on_recovery')
    await wrapper.get('[data-testid="settings-alert-policy-save"]').trigger('click')
    await flushPromises()

    expect(updateDocumentMock).toHaveBeenCalledWith(
      'system',
      0,
      'system.alert_policies',
      {
        ae3_operational_resolution_mode: 'auto_resolve_on_recovery',
      },
    )
  })
})
