import { logger } from '@/utils/logger'
import type {
  ChannelControl,
  ChannelKind,
  GlobalChannelRegistry,
} from '@/ws/subscriptionTypes'

const COMMAND_STATUS_EVENT = '.App\\Events\\CommandStatusUpdated'
const COMMAND_FAILED_EVENT = '.App\\Events\\CommandFailed'
const GLOBAL_EVENT_CREATED = '.App\\Events\\EventCreated'

interface ChannelControlManagerDeps {
  isBrowser: () => boolean
  getEcho: () => any | null
  isGlobalChannel: (channelName: string) => boolean
  channelControls: Map<string, ChannelControl>
  globalChannelRegistry: Map<string, GlobalChannelRegistry>
  onCommandEvent: (channelName: string, payload: any, isFailure: boolean) => void
  onGlobalEvent: (channelName: string, payload: any) => void
}

export function createChannelControlManager(deps: ChannelControlManagerDeps) {
  const getPusherChannel = (channelName: string): any | null => {
    if (!deps.isBrowser()) {
      return null
    }

    const channels = deps.getEcho()?.connector?.pusher?.channels?.channels
    if (!channels) {
      return null
    }

    // Pusher хранит private/presence каналы с префиксом, поэтому проверяем оба варианта
    return (
      channels[channelName] ||
      channels[`private-${channelName}`] ||
      channels[`presence-${channelName}`] ||
      null
    )
  }

  const isChannelDead = (channelName: string): boolean => {
    if (!deps.isBrowser()) {
      return true
    }

    if (!deps.getEcho()) {
      return true
    }

    const pusherChannel = getPusherChannel(channelName)
    if (!pusherChannel) {
      return true
    }

    const hasBindings = Array.isArray(pusherChannel.bindings) && pusherChannel.bindings.length > 0
    const hasCallbacks =
      pusherChannel._callbacks && Object.keys(pusherChannel._callbacks).length > 0
    const hasEvents =
      pusherChannel._events && Object.keys(pusherChannel._events).length > 0

    return !(hasBindings || hasCallbacks || hasEvents)
  }

  const removeChannelListeners = (control: ChannelControl): void => {
    const channel = control.echoChannel
    if (!channel || !control.listenerRefs) {
      return
    }
    Object.keys(control.listenerRefs).forEach(eventName => {
      try {
        channel.stopListening(eventName)
      } catch {
        // ignore stop listening errors
      }
    })
    control.listenerRefs = {}
  }

  const attachChannelListeners = (control: ChannelControl): void => {
    const channel = control.echoChannel
    if (!channel) {
      logger.warn('[useWebSocket] Tried to attach listeners to missing channel', {
        channel: control.channelName,
      })
      return
    }

    removeChannelListeners(control)

    if (control.kind === 'zoneCommands') {
      const statusHandler = (payload: any) => deps.onCommandEvent(control.channelName, payload, false)
      const failedHandler = (payload: any) => deps.onCommandEvent(control.channelName, payload, true)
      channel.listen(COMMAND_STATUS_EVENT, statusHandler)
      channel.listen(COMMAND_FAILED_EVENT, failedHandler)
      control.listenerRefs = {
        [COMMAND_STATUS_EVENT]: statusHandler,
        [COMMAND_FAILED_EVENT]: failedHandler,
      }
      return
    }

    const eventHandler = (payload: any) => deps.onGlobalEvent(control.channelName, payload)
    channel.listen(GLOBAL_EVENT_CREATED, eventHandler)
    control.listenerRefs = {
      [GLOBAL_EVENT_CREATED]: eventHandler,
    }
  }

  const detachChannel = (control: ChannelControl, removeControl = false): void => {
    removeChannelListeners(control)
    if (deps.isBrowser()) {
      try {
        deps.getEcho()?.leave?.(control.channelName)
      } catch {
        // ignore leave errors
      }
    }
    control.echoChannel = null
    if (removeControl) {
      deps.channelControls.delete(control.channelName)
    }
  }

  const ensureChannelControl = (
    channelName: string,
    kind: ChannelKind,
    channelType: 'private' | 'public'
  ): ChannelControl | null => {
    if (!deps.isBrowser()) {
      return null
    }

    if (deps.isGlobalChannel(channelName)) {
      const registry = deps.globalChannelRegistry.get(channelName)
      if (registry && registry.channelControl) {
        const channelStillActive = registry.channelControl.echoChannel && !isChannelDead(channelName)
        if (channelStillActive) {
          logger.debug('[useWebSocket] Reusing existing global channel from registry', {
            channel: channelName,
            refCount: registry.subscriptionRefCount,
            isAuthorized: registry.isAuthorized,
            hasActiveChannel: true,
          })
          return registry.channelControl
        }
        if (registry.channelControl.echoChannel === null) {
          logger.debug('[useWebSocket] Global channel was detached, clearing registry', {
            channel: channelName,
          })
          deps.globalChannelRegistry.delete(channelName)
        }
      }
    }

    let control = deps.channelControls.get(channelName)
    if (!control) {
      control = {
        channelName,
        channelType,
        kind,
        echoChannel: null,
        listenerRefs: {},
      }
      deps.channelControls.set(channelName, control)
    }

    const echo = deps.getEcho()
    if (!echo) {
      if (control.echoChannel) {
        control.echoChannel = null
      }
      return null
    }

    const shouldRecreate = !control.echoChannel || isChannelDead(channelName)

    if (control.echoChannel && !getPusherChannel(channelName)) {
      logger.debug('[useWebSocket] Channel not found in current Echo instance, marking as dead', {
        channel: channelName,
      })
      control.echoChannel = null
    }

    if (shouldRecreate || !control.echoChannel) {
      if (deps.isGlobalChannel(channelName)) {
        const registry = deps.globalChannelRegistry.get(channelName)
        if (
          registry &&
          registry.channelControl &&
          registry.channelControl.echoChannel &&
          !isChannelDead(channelName)
        ) {
          logger.debug('[useWebSocket] Reusing global channel from registry (ref-count was 0)', {
            channel: channelName,
            kind,
            refCount: registry.subscriptionRefCount,
          })
          return registry.channelControl
        }
      }

      control.echoChannel =
        channelType === 'private' ? echo.private(channelName) : echo.channel(channelName)

      if (deps.isGlobalChannel(channelName)) {
        if (!deps.globalChannelRegistry.has(channelName)) {
          deps.globalChannelRegistry.set(channelName, {
            channelControl: control,
            subscriptionRefCount: 0,
            isAuthorized: false,
            handlers: new Set(),
          })
        }
        const registry = deps.globalChannelRegistry.get(channelName)
        if (registry) {
          registry.channelControl = control
          registry.isAuthorized = true
        }

        logger.debug('[useWebSocket] Created global channel (first auth request)', {
          channel: channelName,
          kind,
        })
      } else {
        logger.debug('[useWebSocket] Created channel subscription', {
          channel: channelName,
          kind,
        })
      }
    }

    if (!Object.keys(control.listenerRefs).length || shouldRecreate) {
      attachChannelListeners(control)
    }

    return control
  }

  const resubscribeAllChannels = (): void => {
    if (!deps.isBrowser()) {
      return
    }

    const echo = deps.getEcho()
    if (!echo) {
      logger.debug('[useWebSocket] resubscribe skipped: Echo not yet initialized', {
        readyState: document.readyState,
      })
      return
    }

    deps.channelControls.forEach(control => {
      try {
        removeChannelListeners(control)

        if (control.echoChannel) {
          try {
            if (deps.isBrowser() && deps.getEcho()) {
              deps.getEcho()?.leave?.(control.channelName)
            }
          } catch {
            // ignore leave errors
          }
          control.echoChannel = null
        }

        control.echoChannel =
          control.channelType === 'private'
            ? echo.private(control.channelName)
            : echo.channel(control.channelName)

        attachChannelListeners(control)
        logger.debug('[useWebSocket] Resubscribed channel', { channel: control.channelName })
      } catch (error) {
        logger.error('[useWebSocket] Failed to resubscribe channel', {
          channel: control.channelName,
        }, error)
      }
    })
  }

  return {
    ensureChannelControl,
    detachChannel,
    removeChannelListeners,
    isChannelDead,
    resubscribeAllChannels,
  }
}
