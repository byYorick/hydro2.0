import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AuthorityFieldCatalogForm from '@/Components/Settings/AuthorityFieldCatalogForm.vue'
import type { SystemSettingsSection } from '@/types/SystemSettings'

const sections: SystemSettingsSection[] = [
  {
    key: 'observability_commands',
    label: 'Команды',
    description: 'Пороги команд AE3.',
    fields: [
      {
        path: 'waiting_command_warn_sec',
        label: 'Waiting command — warning',
        description: 'Ожидание command_response.',
        help: 'Подробный текст подсказки для оператора.',
        type: 'integer',
        min: 30,
        max: 3600,
        unit: 'сек',
      },
    ],
  },
]

describe('AuthorityFieldCatalogForm', () => {
  const manySections: SystemSettingsSection[] = [
    ...sections,
    {
      key: 'observability_snapshot',
      label: 'Снимок',
      description: 'Пороги снимка.',
      fields: [
        {
          path: 'snapshot_stale_sec',
          label: 'Снимок устарел',
          description: 'Возраст снимка.',
          type: 'integer',
          unit: 'сек',
        },
      ],
    },
  ]

  it('renders section headers and field descriptions', async () => {
    const wrapper = mount(AuthorityFieldCatalogForm, {
      props: {
        sections,
        modelValue: {
          waiting_command_warn_sec: 120,
        },
      },
    })

    expect(wrapper.text()).toContain('Команды')
    expect(wrapper.text()).toContain('Waiting command — warning')
    expect(wrapper.get('[data-testid="authority-field-waiting_command_warn_sec"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="authority-field-help-waiting_command_warn_sec"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="authority-section-help-observability_commands"]').exists()).toBe(true)

    await wrapper.get('[data-testid="authority-section-help-observability_commands"]').trigger('click')
    expect(wrapper.text()).toContain('Пороги команд AE3.')

    await wrapper.get('[data-testid="authority-field-help-waiting_command_warn_sec"]').trigger('click')
    expect(wrapper.text()).toContain('Ожидание command_response.')
  })

  it('оставляет первую секцию открытой, остальные сворачивает', () => {
    const wrapper = mount(AuthorityFieldCatalogForm, {
      props: {
        sections: manySections,
        modelValue: {
          waiting_command_warn_sec: 120,
          snapshot_stale_sec: 60,
        },
      },
    })

    expect(wrapper.find('[data-testid="authority-field-waiting_command_warn_sec"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="authority-field-snapshot_stale_sec"]').exists()).toBe(false)
  })
})
