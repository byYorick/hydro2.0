/// <reference types="vite/client" />
/// <reference types="vitest/globals" />

import type {} from 'axios'

declare global {
  interface Window {
    __echartsTooltipStyleAdded?: boolean
    __logsPollInterval__?: ReturnType<typeof setInterval> | null
    __logsSearchDebounce__?: ReturnType<typeof setTimeout> | null
  }

  /** Blade `@routes` / Ziggy config (optional until install). */
  // eslint-disable-next-line no-var
  var Ziggy: unknown
}

declare module 'axios' {
  interface AxiosRequestConfig {
    /** Не показывать глобальный error-toast (caller покажет своё UI). */
    skipErrorToast?: boolean
  }
}

declare module '@/utils/formatTime' {
  export function formatTime(dateString?: string | Date | null): string
  export function formatTimeShort(timestamp?: string | Date | null): string
  export function formatInterval(seconds?: number | null): string
  export function formatTimeAgo(timestamp?: number | string | Date | null): string
}

declare module '@/utils/i18n' {
  export function translateStatus(status: string): string
  export function classifyEventKind(kind: string): 'ALERT' | 'WARNING' | 'INFO' | 'ACTION'
  export function translateEventKind(kind: string): string
  export function translateRole(role: string): string
  export function translateCycleType(cycleType: string): string
  export function translateStrategy(strategy: string): string
  export function translateDeviceType(type: string): string
  export function translateWorkflowStage(value: string): string
}

declare module '../../../vendor/tightenco/ziggy/dist/index.esm.js' {
  export const ZiggyVue: { install: (...args: unknown[]) => void } | ((...args: unknown[]) => unknown)
  const defaultExport: unknown
  export default defaultExport
}

export {}
