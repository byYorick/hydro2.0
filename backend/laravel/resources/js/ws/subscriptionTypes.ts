import type { ToastHandler } from '@/composables/useApi'

export type WsEventPayload = Record<string, unknown>

export interface EchoChannelLike {
  listen: (event: string, callback: (payload: WsEventPayload) => void) => unknown
  stopListening: (event: string, callback?: (payload: WsEventPayload) => void) => unknown
}

export interface PusherChannelSnapshot {
  bindings?: unknown[]
  _callbacks?: Record<string, unknown>
  _events?: Record<string, unknown>
}

export interface EchoLike {
  private: (channel: string) => EchoChannelLike
  channel: (channel: string) => EchoChannelLike
  leave?: (channel: string) => void
  connector?: {
    pusher?: {
      channels?: {
        channels?: Record<string, unknown>
      }
      connection?: {
        state?: string
        socket_id?: string | null
        connect?: () => void
      }
      connect?: () => void
      disconnect?: () => void
    }
  }
}

export type ZoneCommandHandler = (event: {
  commandId: number | string
  status: string
  message?: string
  error?: string
  zoneId?: number
}) => void

export type GlobalEventHandler = (event: {
  id: number | string
  kind: string
  message: string
  zoneId?: number
  occurredAt: string
}) => void

export type ChannelKind = 'zoneCommands' | 'globalEvents'

export interface ActiveSubscription {
  id: string
  channelName: string
  kind: ChannelKind
  handler: ZoneCommandHandler | GlobalEventHandler
  componentTag: string
  showToast?: ToastHandler
  instanceId: number
}

export interface ChannelControl {
  channelName: string
  channelType: 'private' | 'public'
  kind: ChannelKind
  echoChannel: EchoChannelLike | null
  listenerRefs: Record<string, (payload: WsEventPayload) => void>
}

export interface GlobalChannelRegistry {
  channelControl: ChannelControl | null
  subscriptionRefCount: number
  isAuthorized: boolean
  handlers: Set<GlobalEventHandler>
}

export interface PendingSubscription {
  id: string
  channelName: string
  kind: ChannelKind
  channelType: 'private' | 'public'
  handler: ZoneCommandHandler | GlobalEventHandler
  componentTag: string
  instanceId: number
  showToast?: ToastHandler
}
