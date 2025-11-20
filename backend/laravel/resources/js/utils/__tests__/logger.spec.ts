import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import * as loggerModule from '../logger'

describe('logger', () => {
  let originalEnv: typeof import.meta.env
  let consoleLogSpy: ReturnType<typeof vi.spyOn>
  let consoleWarnSpy: ReturnType<typeof vi.spyOn>
  let consoleErrorSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    consoleLogSpy = vi.spyOn(console, 'log').mockImplementation(() => {})
    consoleWarnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    originalEnv = import.meta.env
  })

  afterEach(() => {
    vi.restoreAllMocks()
    Object.defineProperty(import.meta, 'env', {
      value: originalEnv,
      writable: true,
      configurable: true,
    })
  })

  describe('in development mode', () => {
    beforeEach(() => {
      Object.defineProperty(import.meta, 'env', {
        value: { ...originalEnv, DEV: true, PROD: false },
        writable: true,
        configurable: true,
      })
    })

    it('should log debug messages', () => {
      loggerModule.debug('test debug')
      expect(consoleLogSpy).toHaveBeenCalledWith('[DEBUG]', 'test debug')
    })

    it('should log info messages', () => {
      loggerModule.info('test info')
      expect(consoleLogSpy).toHaveBeenCalledWith('[INFO]', 'test info')
    })

    it('should log warn messages', () => {
      loggerModule.warn('test warn')
      expect(consoleWarnSpy).toHaveBeenCalledWith('[WARN]', 'test warn')
    })

    it('should log error messages', () => {
      loggerModule.error('test error')
      expect(consoleErrorSpy).toHaveBeenCalledWith('[ERROR]', 'test error')
    })

    it('should support group methods', () => {
      loggerModule.group('test group')
      expect(consoleLogSpy).toHaveBeenCalled()
      loggerModule.groupEnd()
    })

    it('should support table method', () => {
      const data = { a: 1, b: 2 }
      loggerModule.table(data)
      expect(consoleLogSpy).toHaveBeenCalled()
    })

    it('should support time methods', () => {
      loggerModule.time('test')
      loggerModule.timeEnd('test')
      expect(consoleLogSpy).toHaveBeenCalled()
    })

    it('should expose isDev and isProd properties', () => {
      expect(loggerModule.logger.isDev).toBe(true)
      expect(loggerModule.logger.isProd).toBe(false)
    })
  })

  describe('in production mode', () => {
    beforeEach(() => {
      Object.defineProperty(import.meta, 'env', {
        value: { ...originalEnv, DEV: false, PROD: true },
        writable: true,
        configurable: true,
      })
    })

    it('should not log debug messages', () => {
      loggerModule.debug('test debug')
      expect(consoleLogSpy).not.toHaveBeenCalled()
    })

    it('should not log info messages', () => {
      loggerModule.info('test info')
      expect(consoleLogSpy).not.toHaveBeenCalled()
    })

    it('should still log warn messages', () => {
      loggerModule.warn('test warn')
      expect(consoleWarnSpy).toHaveBeenCalledWith('[WARN]', 'test warn')
    })

    it('should still log error messages', () => {
      loggerModule.error('test error')
      expect(consoleErrorSpy).toHaveBeenCalledWith('[ERROR]', 'test error')
    })

    it('should not call group methods', () => {
      loggerModule.group('test group')
      expect(consoleLogSpy).not.toHaveBeenCalled()
    })

    it('should expose isDev and isProd properties', () => {
      expect(loggerModule.logger.isDev).toBe(false)
      expect(loggerModule.logger.isProd).toBe(true)
    })
  })

  describe('logger object', () => {
    it('should export all methods', () => {
      expect(loggerModule.logger).toHaveProperty('debug')
      expect(loggerModule.logger).toHaveProperty('info')
      expect(loggerModule.logger).toHaveProperty('warn')
      expect(loggerModule.logger).toHaveProperty('error')
      expect(loggerModule.logger).toHaveProperty('group')
      expect(loggerModule.logger).toHaveProperty('groupEnd')
      expect(loggerModule.logger).toHaveProperty('table')
      expect(loggerModule.logger).toHaveProperty('time')
      expect(loggerModule.logger).toHaveProperty('timeEnd')
    })
  })
})

