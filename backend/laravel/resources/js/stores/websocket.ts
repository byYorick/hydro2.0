import { defineStore } from 'pinia'

export type WsConnectionState = 'connected' | 'connecting' | 'retrying' | 'failed' | 'disconnected'

interface WebSocketStoreState {
  state: WsConnectionState
  reconnectAttempts: number
  lastError: {
    message: string
    code?: number
    timestamp: number
  } | null
  socketId: string | null
  protocol?: string
  port?: number
  host?: string
}

export const useWebSocketStore = defineStore('websocket', {
  state: (): WebSocketStoreState => ({
    state: 'disconnected',
    reconnectAttempts: 0,
    lastError: null,
    socketId: null,
    protocol: undefined,
    port: undefined,
    host: undefined,
  }),
  actions: {
    setState(state: WsConnectionState): void {
      this.state = state
    },
    setReconnectAttempts(attempts: number): void {
      this.reconnectAttempts = attempts
    },
    setLastError(error: { message: string; code?: number; timestamp: number } | null): void {
      this.lastError = error
    },
    setSocketId(socketId: string | null): void {
      this.socketId = socketId
    },
    setConnectionInfo(info: { protocol?: string; port?: number; host?: string }): void {
      if (info.protocol !== undefined) this.protocol = info.protocol
      if (info.port !== undefined) this.port = info.port
      if (info.host !== undefined) this.host = info.host
    },
    reset(): void {
      this.state = 'disconnected'
      this.reconnectAttempts = 0
      this.lastError = null
      this.socketId = null
      this.protocol = undefined
      this.port = undefined
      this.host = undefined
    },
  },
  getters: {
    isConnected: (state): boolean => state.state === 'connected',
    isConnecting: (state): boolean => state.state === 'connecting' || state.state === 'retrying',
    isFailed: (state): boolean => state.state === 'failed',
    isDisconnected: (state): boolean => state.state === 'disconnected',
  },
})

