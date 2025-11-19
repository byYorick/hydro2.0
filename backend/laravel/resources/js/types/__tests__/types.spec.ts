import { describe, it, expect } from 'vitest'
import type {
  Zone,
  Device,
  Alert,
  Recipe,
  Command,
  Telemetry,
  User,
  Greenhouse,
  Event,
  Cycle
} from '../index'

describe('Type Definitions (P1-1)', () => {
  describe('Zone type', () => {
    it('should have required fields', () => {
      const zone: Zone = {
        id: 1,
        name: 'Test Zone',
        status: 'RUNNING',
        uid: 'zone-1',
        greenhouse_id: 1,
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z'
      }

      expect(zone.id).toBe(1)
      expect(zone.name).toBe('Test Zone')
      expect(zone.status).toBe('RUNNING')
    })

    it('should allow optional fields', () => {
      const zone: Zone = {
        id: 1,
        name: 'Test Zone',
        status: 'RUNNING',
        uid: 'zone-1',
        greenhouse_id: 1,
        description: 'Test description',
        settings: {},
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z'
      }

      expect(zone.description).toBe('Test description')
      expect(zone.settings).toBeDefined()
    })
  })

  describe('Device type', () => {
    it('should have required fields', () => {
      const device: Device = {
        id: 1,
        uid: 'device-1',
        type: 'sensor',
        status: 'online',
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z'
      }

      expect(device.id).toBe(1)
      expect(device.uid).toBe('device-1')
      expect(device.type).toBe('sensor')
      expect(device.status).toBe('online')
    })
  })

  describe('Alert type', () => {
    it('should have required fields', () => {
      const alert: Alert = {
        id: 1,
        type: 'WARNING',
        status: 'ACTIVE',
        zone_id: 1,
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z'
      }

      expect(alert.id).toBe(1)
      expect(alert.type).toBe('WARNING')
      expect(alert.status).toBe('ACTIVE')
    })
  })

  describe('Recipe type', () => {
    it('should have required fields', () => {
      const recipe: Recipe = {
        id: 1,
        name: 'Test Recipe',
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z'
      }

      expect(recipe.id).toBe(1)
      expect(recipe.name).toBe('Test Recipe')
    })
  })

  describe('Command type', () => {
    it('should have required fields', () => {
      const command: Command = {
        id: 1,
        zone_id: 1,
        type: 'FORCE_IRRIGATION',
        status: 'pending',
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z'
      }

      expect(command.id).toBe(1)
      expect(command.zone_id).toBe(1)
      expect(command.type).toBe('FORCE_IRRIGATION')
      expect(command.status).toBe('pending')
    })
  })

  describe('Telemetry types', () => {
    it('should have ZoneTelemetry structure', () => {
      const telemetry: Telemetry = {
        ph: 6.5,
        ec: 1.5,
        temperature: 22,
        humidity: 60
      }

      expect(telemetry.ph).toBe(6.5)
      expect(telemetry.ec).toBe(1.5)
      expect(telemetry.temperature).toBe(22)
      expect(telemetry.humidity).toBe(60)
    })
  })

  describe('Event type', () => {
    it('should have required fields', () => {
      const event: Event = {
        id: 1,
        kind: 'INFO',
        message: 'Test event',
        zone_id: 1,
        occurred_at: '2024-01-01T00:00:00Z'
      }

      expect(event.id).toBe(1)
      expect(event.kind).toBe('INFO')
      expect(event.message).toBe('Test event')
    })
  })

  describe('Cycle type', () => {
    it('should have required fields', () => {
      const cycle: Cycle = {
        type: 'IRRIGATION',
        strategy: 'periodic',
        interval: 300
      }

      expect(cycle.type).toBe('IRRIGATION')
      expect(cycle.strategy).toBe('periodic')
      expect(cycle.interval).toBe(300)
    })
  })
})

