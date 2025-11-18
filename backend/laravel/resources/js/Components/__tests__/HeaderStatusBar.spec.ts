import { mount } from '@vue/test-utils'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import HeaderStatusBar from '../HeaderStatusBar.vue'

// Mock useSystemStatus
const mockUseSystemStatus = vi.fn(() => ({
  coreStatus: { value: 'ok' },
  dbStatus: { value: 'ok' },
  wsStatus: { value: 'connected' },
  mqttStatus: { value: 'online' },
  lastUpdate: { value: new Date('2024-01-01T12:00:00Z') }
}))

vi.mock('@/composables/useSystemStatus', () => ({
  useSystemStatus: mockUseSystemStatus
}))

// Mock formatTime
vi.mock('@/utils/formatTime', () => ({
  formatTime: vi.fn((date) => {
    if (!date) return ''
    return 'только что'
  })
}))

describe('HeaderStatusBar', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders all status indicators', () => {
    const wrapper = mount(HeaderStatusBar)
    
    expect(wrapper.text()).toContain('Core')
    expect(wrapper.text()).toContain('DB')
    expect(wrapper.text()).toContain('WS')
    expect(wrapper.text()).toContain('MQTT')
  })

  it('displays core status with correct color for ok', () => {
    mockUseSystemStatus.mockReturnValue({
      coreStatus: { value: 'ok' },
      dbStatus: { value: 'ok' },
      wsStatus: { value: 'connected' },
      mqttStatus: { value: 'online' },
      lastUpdate: { value: new Date() }
    })

    const wrapper = mount(HeaderStatusBar)
    const coreDot = wrapper.find('.bg-emerald-400')
    expect(coreDot.exists()).toBe(true)
  })

  it('displays core status with correct color for fail', () => {
    mockUseSystemStatus.mockReturnValue({
      coreStatus: { value: 'fail' },
      dbStatus: { value: 'ok' },
      wsStatus: { value: 'connected' },
      mqttStatus: { value: 'online' },
      lastUpdate: { value: new Date() }
    })

    const wrapper = mount(HeaderStatusBar)
    const coreDot = wrapper.find('.bg-red-400')
    expect(coreDot.exists()).toBe(true)
  })

  it('displays core status with correct color for unknown', () => {
    mockUseSystemStatus.mockReturnValue({
      coreStatus: { value: 'unknown' },
      dbStatus: { value: 'ok' },
      wsStatus: { value: 'connected' },
      mqttStatus: { value: 'online' },
      lastUpdate: { value: new Date() }
    })

    const wrapper = mount(HeaderStatusBar)
    const coreDot = wrapper.find('.bg-neutral-500')
    expect(coreDot.exists()).toBe(true)
  })

  it('displays database status correctly', () => {
    mockUseSystemStatus.mockReturnValue({
      coreStatus: { value: 'ok' },
      dbStatus: { value: 'fail' },
      wsStatus: { value: 'connected' },
      mqttStatus: { value: 'online' },
      lastUpdate: { value: new Date() }
    })

    const wrapper = mount(HeaderStatusBar)
    const dbDots = wrapper.findAll('.bg-red-400')
    // Должен быть хотя бы один красный индикатор (для DB)
    expect(dbDots.length).toBeGreaterThan(0)
  })

  it('displays WebSocket status correctly', () => {
    mockUseSystemStatus.mockReturnValue({
      coreStatus: { value: 'ok' },
      dbStatus: { value: 'ok' },
      wsStatus: { value: 'disconnected' },
      mqttStatus: { value: 'online' },
      lastUpdate: { value: new Date() }
    })

    const wrapper = mount(HeaderStatusBar)
    const wsDots = wrapper.findAll('.bg-red-400')
    // Должен быть красный индикатор для WebSocket
    expect(wsDots.length).toBeGreaterThan(0)
  })

  it('displays MQTT status correctly', () => {
    mockUseSystemStatus.mockReturnValue({
      coreStatus: { value: 'ok' },
      dbStatus: { value: 'ok' },
      wsStatus: { value: 'connected' },
      mqttStatus: { value: 'offline' },
      lastUpdate: { value: new Date() }
    })

    const wrapper = mount(HeaderStatusBar)
    const mqttDots = wrapper.findAll('.bg-red-400')
    // Должен быть красный индикатор для MQTT
    expect(mqttDots.length).toBeGreaterThan(0)
  })

  it('displays MQTT degraded status with amber color', () => {
    mockUseSystemStatus.mockReturnValue({
      coreStatus: { value: 'ok' },
      dbStatus: { value: 'ok' },
      wsStatus: { value: 'connected' },
      mqttStatus: { value: 'degraded' },
      lastUpdate: { value: new Date() }
    })

    const wrapper = mount(HeaderStatusBar)
    const degradedDot = wrapper.find('.bg-amber-400')
    expect(degradedDot.exists()).toBe(true)
  })

  it('shows tooltip with last update time when lastUpdate is available', () => {
    const { useSystemStatus } = require('@/composables/useSystemStatus')
    const lastUpdate = new Date('2024-01-01T12:00:00Z')
    useSystemStatus.mockReturnValue({
      coreStatus: { value: 'ok' },
      dbStatus: { value: 'ok' },
      wsStatus: { value: 'connected' },
      mqttStatus: { value: 'online' },
      lastUpdate: { value: lastUpdate }
    })

    const wrapper = mount(HeaderStatusBar)
    const tooltips = wrapper.findAll('.absolute')
    // Должны быть tooltips для каждого статуса
    expect(tooltips.length).toBeGreaterThan(0)
    expect(wrapper.text()).toContain('Обновлено:')
  })

  it('does not show tooltip when lastUpdate is null', () => {
    mockUseSystemStatus.mockReturnValue({
      coreStatus: { value: 'ok' },
      dbStatus: { value: 'ok' },
      wsStatus: { value: 'connected' },
      mqttStatus: { value: 'online' },
      lastUpdate: { value: null }
    })

    const wrapper = mount(HeaderStatusBar)
    // Tooltips не должны отображаться, если lastUpdate null
    const tooltips = wrapper.findAll('.absolute')
    // v-if="lastUpdate" должен скрыть tooltips
    expect(tooltips.length).toBe(0)
  })

  it('applies correct title attributes for status indicators', () => {
    mockUseSystemStatus.mockReturnValue({
      coreStatus: { value: 'ok' },
      dbStatus: { value: 'ok' },
      wsStatus: { value: 'connected' },
      mqttStatus: { value: 'online' },
      lastUpdate: { value: new Date() }
    })

    const wrapper = mount(HeaderStatusBar)
    
    // Проверяем наличие title атрибутов
    const statusDots = wrapper.findAll('[title]')
    expect(statusDots.length).toBeGreaterThan(0)
    
    // Проверяем, что title содержит правильный текст
    const coreDot = statusDots.find(dot => dot.attributes('title')?.includes('Core'))
    expect(coreDot).toBeDefined()
  })

  it('hides status labels on small screens', () => {
    mockUseSystemStatus.mockReturnValue({
      coreStatus: { value: 'ok' },
      dbStatus: { value: 'ok' },
      wsStatus: { value: 'connected' },
      mqttStatus: { value: 'online' },
      lastUpdate: { value: new Date() }
    })

    const wrapper = mount(HeaderStatusBar)
    
    // Проверяем, что labels имеют класс hidden sm:inline
    const labels = wrapper.findAll('.hidden.sm\\:inline')
    expect(labels.length).toBeGreaterThan(0)
  })

  it('renders all four status indicators', () => {
    mockUseSystemStatus.mockReturnValue({
      coreStatus: { value: 'ok' },
      dbStatus: { value: 'ok' },
      wsStatus: { value: 'connected' },
      mqttStatus: { value: 'online' },
      lastUpdate: { value: new Date() }
    })

    const wrapper = mount(HeaderStatusBar)
    
    // Должно быть 4 индикатора статуса (Core, DB, WS, MQTT)
    const statusGroups = wrapper.findAll('.group.relative')
    expect(statusGroups.length).toBe(4)
  })

  it('handles all status combinations correctly', () => {
    const { useSystemStatus } = require('@/composables/useSystemStatus')
    
    // Тестируем различные комбинации статусов
    const combinations = [
      { core: 'ok', db: 'ok', ws: 'connected', mqtt: 'online' },
      { core: 'fail', db: 'ok', ws: 'connected', mqtt: 'online' },
      { core: 'ok', db: 'fail', ws: 'disconnected', mqtt: 'offline' },
      { core: 'unknown', db: 'unknown', ws: 'unknown', mqtt: 'unknown' },
      { core: 'ok', db: 'ok', ws: 'connected', mqtt: 'degraded' },
    ]

    combinations.forEach(combo => {
      useSystemStatus.mockReturnValue({
        coreStatus: { value: combo.core },
        dbStatus: { value: combo.db },
        wsStatus: { value: combo.ws },
        mqttStatus: { value: combo.mqtt },
        lastUpdate: { value: new Date() }
      })

      const wrapper = mount(HeaderStatusBar)
      expect(wrapper.exists()).toBe(true)
      expect(wrapper.text()).toContain('Core')
    })
  })
})

