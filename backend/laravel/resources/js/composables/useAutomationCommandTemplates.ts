import { computed, ref } from 'vue'
import { useAutomationConfig } from '@/composables/useAutomationConfig'
import type {
  AutomationCommandTemplateStep,
  AutomationCommandTemplatesSettings,
} from '@/types/SystemSettings'

const authorityCommandTemplates = ref<Partial<AutomationCommandTemplatesSettings> | null>(null)
let authorityCommandTemplatesRequest: Promise<void> | null = null

export const FALLBACK_AUTOMATION_COMMAND_TEMPLATES: AutomationCommandTemplatesSettings = {
  irrigation_start: [
    { channel: 'valve_solution_supply', cmd: 'set_relay', params: { state: true } },
    { channel: 'valve_irrigation', cmd: 'set_relay', params: { state: true } },
    { channel: 'pump_main', cmd: 'set_relay', params: { state: true } },
  ],
  irrigation_stop: [
    { channel: 'pump_main', cmd: 'set_relay', params: { state: false } },
    { channel: 'valve_irrigation', cmd: 'set_relay', params: { state: false } },
    { channel: 'valve_solution_supply', cmd: 'set_relay', params: { state: false } },
  ],
  clean_fill_start: [
    { channel: 'valve_clean_fill', cmd: 'set_relay', params: { state: true } },
  ],
  clean_fill_stop: [
    { channel: 'valve_clean_fill', cmd: 'set_relay', params: { state: false } },
  ],
  solution_fill_start: [
    { channel: 'valve_clean_supply', cmd: 'set_relay', params: { state: true } },
    { channel: 'valve_solution_fill', cmd: 'set_relay', params: { state: true } },
    { channel: 'pump_main', cmd: 'set_relay', params: { state: true } },
  ],
  solution_fill_stop: [
    { channel: 'pump_main', cmd: 'set_relay', params: { state: false } },
    { channel: 'valve_solution_fill', cmd: 'set_relay', params: { state: false } },
    { channel: 'valve_clean_supply', cmd: 'set_relay', params: { state: false } },
  ],
  prepare_recirculation_start: [
    { channel: 'valve_solution_supply', cmd: 'set_relay', params: { state: true } },
    { channel: 'valve_solution_fill', cmd: 'set_relay', params: { state: true } },
    { channel: 'pump_main', cmd: 'set_relay', params: { state: true } },
  ],
  prepare_recirculation_stop: [
    { channel: 'pump_main', cmd: 'set_relay', params: { state: false } },
    { channel: 'valve_solution_fill', cmd: 'set_relay', params: { state: false } },
    { channel: 'valve_solution_supply', cmd: 'set_relay', params: { state: false } },
  ],
  irrigation_recovery_start: [
    { channel: 'valve_irrigation', cmd: 'set_relay', params: { state: false } },
    { channel: 'valve_solution_supply', cmd: 'set_relay', params: { state: true } },
    { channel: 'valve_solution_fill', cmd: 'set_relay', params: { state: true } },
    { channel: 'pump_main', cmd: 'set_relay', params: { state: true } },
  ],
  irrigation_recovery_stop: [
    { channel: 'pump_main', cmd: 'set_relay', params: { state: false } },
    { channel: 'valve_solution_fill', cmd: 'set_relay', params: { state: false } },
    { channel: 'valve_solution_supply', cmd: 'set_relay', params: { state: false } },
    { channel: 'valve_irrigation', cmd: 'set_relay', params: { state: true } },
  ],
}

function cloneCommandTemplateStep(step: AutomationCommandTemplateStep): AutomationCommandTemplateStep {
  return {
    channel: step.channel,
    cmd: step.cmd,
    params: {
      state: step.params.state,
    },
  }
}

function normalizeTemplateSteps(value: unknown, fallback: AutomationCommandTemplateStep[]): AutomationCommandTemplateStep[] {
  if (!Array.isArray(value)) {
    return fallback.map(cloneCommandTemplateStep)
  }

  const normalized = value
    .filter((item) => item && typeof item === 'object' && !Array.isArray(item))
    .map((item) => {
      const record = item as Record<string, unknown>
      return {
        channel: typeof record.channel === 'string' ? record.channel : '',
        cmd: record.cmd === 'set_relay' ? 'set_relay' : 'set_relay',
        params: {
          state: Boolean((record.params as Record<string, unknown> | undefined)?.state),
        },
      } satisfies AutomationCommandTemplateStep
    })
    .filter((item) => item.channel.trim() !== '')

  return normalized.length > 0 ? normalized : fallback.map(cloneCommandTemplateStep)
}

export function normalizeAutomationCommandTemplates(
  raw: Partial<AutomationCommandTemplatesSettings> | null | undefined,
): AutomationCommandTemplatesSettings {
  return {
    irrigation_start: normalizeTemplateSteps(raw?.irrigation_start, FALLBACK_AUTOMATION_COMMAND_TEMPLATES.irrigation_start),
    irrigation_stop: normalizeTemplateSteps(raw?.irrigation_stop, FALLBACK_AUTOMATION_COMMAND_TEMPLATES.irrigation_stop),
    clean_fill_start: normalizeTemplateSteps(raw?.clean_fill_start, FALLBACK_AUTOMATION_COMMAND_TEMPLATES.clean_fill_start),
    clean_fill_stop: normalizeTemplateSteps(raw?.clean_fill_stop, FALLBACK_AUTOMATION_COMMAND_TEMPLATES.clean_fill_stop),
    solution_fill_start: normalizeTemplateSteps(raw?.solution_fill_start, FALLBACK_AUTOMATION_COMMAND_TEMPLATES.solution_fill_start),
    solution_fill_stop: normalizeTemplateSteps(raw?.solution_fill_stop, FALLBACK_AUTOMATION_COMMAND_TEMPLATES.solution_fill_stop),
    prepare_recirculation_start: normalizeTemplateSteps(
      raw?.prepare_recirculation_start,
      FALLBACK_AUTOMATION_COMMAND_TEMPLATES.prepare_recirculation_start
    ),
    prepare_recirculation_stop: normalizeTemplateSteps(
      raw?.prepare_recirculation_stop,
      FALLBACK_AUTOMATION_COMMAND_TEMPLATES.prepare_recirculation_stop
    ),
    irrigation_recovery_start: normalizeTemplateSteps(
      raw?.irrigation_recovery_start,
      FALLBACK_AUTOMATION_COMMAND_TEMPLATES.irrigation_recovery_start
    ),
    irrigation_recovery_stop: normalizeTemplateSteps(
      raw?.irrigation_recovery_stop,
      FALLBACK_AUTOMATION_COMMAND_TEMPLATES.irrigation_recovery_stop
    ),
  }
}

export function useAutomationCommandTemplates() {
  const automationConfig = useAutomationConfig()
  if (authorityCommandTemplates.value === null && authorityCommandTemplatesRequest === null) {
    authorityCommandTemplatesRequest = automationConfig
      .getDocument<Partial<AutomationCommandTemplatesSettings>>('system', 0, 'system.command_templates')
      .then((document) => {
        authorityCommandTemplates.value = document.payload ?? null
      })
      .catch(() => {})
      .finally(() => {
        authorityCommandTemplatesRequest = null
      })
  }

  return computed(() => normalizeAutomationCommandTemplates(authorityCommandTemplates.value))
}
