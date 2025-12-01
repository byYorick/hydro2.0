import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

type LoggerModule = typeof import('../logger')
let loggerModule: LoggerModule
const loadLoggerModule = async () => {
  vi.resetModules()
  return await import('../logger')
}

describe('logger', () => {
  let originalEnv: Record<string, any>
  let consoleLogSpy: ReturnType<typeof vi.spyOn>
  let consoleWarnSpy: ReturnType<typeof vi.spyOn>
  let consoleErrorSpy: ReturnType<typeof vi.spyOn>

  beforeEach(async () => {
    consoleLogSpy = vi.spyOn(console, 'log').mockImplementation(() => {})
    consoleWarnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    originalEnv = { ...import.meta.env }
    loggerModule = await loadLoggerModule()
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
    beforeEach(async () => {
      Object.defineProperty(import.meta, 'env', {
        value: {
          ...originalEnv,
          DEV: true,
          PROD: false,
          VITE_WS_LOG_LEVEL: '',
          VITE_FORCE_DEBUG_LOGS: 'false',
        },
        writable: true,
        configurable: true,
      })
      loggerModule = await loadLoggerModule()
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

  describe('with log level overrides', () => {
    beforeEach(async () => {
      Object.defineProperty(import.meta, 'env', {
        value: {
          ...originalEnv,
          DEV: true,
          PROD: false,
          VITE_WS_LOG_LEVEL: 'warn',
          VITE_FORCE_DEBUG_LOGS: 'false',
        },
        writable: true,
        configurable: true,
      })
      loggerModule = await loadLoggerModule()
    })

    it('should still log warn messages', () => {
      loggerModule.warn('test warn')
      expect(consoleWarnSpy).toHaveBeenCalledWith('[WARN]', 'test warn')
    })

    it('should still log error messages', () => {
      loggerModule.error('test error')
      expect(consoleErrorSpy).toHaveBeenCalledWith('[ERROR]', 'test error')
    })

    it('should expose env flags from vite build', () => {
      expect(loggerModule.logger.isDev).toBe(import.meta.env.DEV)
      expect(loggerModule.logger.isProd).toBe(import.meta.env.PROD)
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

