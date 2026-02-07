import type { ToastHandler } from '@/composables/useApi'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import { getEchoInstance } from '@/utils/echoClient'
import { readBooleanEnv } from '@/utils/env'
import { logger } from '@/utils/logger'
import type { EchoLike } from '@/ws/subscriptionTypes'

export const GLOBAL_EVENTS_CHANNEL = 'events.global'
const COMMANDS_GLOBAL_CHANNEL = 'commands.global'
const WS_DISABLED_MESSAGE = 'Realtime отключен в этой сборке'

export function isGlobalChannel(channelName: string): boolean {
  return channelName === GLOBAL_EVENTS_CHANNEL || channelName === COMMANDS_GLOBAL_CHANNEL
}

export function isBrowser(): boolean {
  return typeof window !== 'undefined'
}

export function isWsEnabled(): boolean {
  return readBooleanEnv('VITE_ENABLE_WS', true)
}

export function getAvailableEcho(): EchoLike | null {
  if (!isBrowser()) {
    return null
  }

  return window.Echo || getEchoInstance()
}

export function ensureEchoAvailable(showToast?: ToastHandler): EchoLike | null {
  if (!isBrowser()) {
    return null
  }

  if (!isWsEnabled()) {
    showToast?.(WS_DISABLED_MESSAGE, 'warning', TOAST_TIMEOUT.NORMAL)
    logger.warn('[useWebSocket] WebSocket disabled via env flag', {})
    return null
  }

  const echo = window.Echo
  if (echo) {
    return echo
  }

  const readyState = typeof document !== 'undefined' ? document.readyState : 'unknown'
  if (readyState === 'loading') {
    logger.debug('[useWebSocket] Echo instance not yet initialized, waiting for bootstrap.js', {
      readyState,
    })
  } else {
    logger.debug('[useWebSocket] Echo instance not yet initialized', {
      readyState,
      hasWindowEcho: false,
    })
  }

  return null
}
