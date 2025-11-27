import { describe, it, expect, beforeEach, vi } from 'vitest'
import {
  initEcho,
  getEcho,
  getEchoInstance,
  getConnectionState,
  getLastError,
  getReconnectAttempts,
  onWsStateChange,
} from '../echoClient'

describe('echoClient stub', () => {
  beforeEach(() => {
    // @ts-ignore
    global.window = {}
  })

  it('returns null from initEcho', () => {
    const result = initEcho()
    expect(result).toBeNull()
    expect(getEcho()).toBeNull()
    expect(getEchoInstance()).toBeNull()
  })

  it('reports disconnected state', () => {
    const state = getConnectionState()
    expect(state.state).toBe('disconnected')
    expect(state.isReconnecting).toBe(false)
    expect(state.reconnectAttempts).toBe(0)
    expect(state.socketId).toBeNull()
  })

  it('exposes noop listener unsubscribe', () => {
    const spy = vi.fn()
    const remove = onWsStateChange(spy)
    remove()
    expect(typeof remove).toBe('function')
  })

  it('returns defaults for error/attempts', () => {
    expect(getReconnectAttempts()).toBe(0)
    expect(getLastError()).toBeNull()
  })
})

