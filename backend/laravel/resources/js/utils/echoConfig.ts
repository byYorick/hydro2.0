import { logger } from './logger'
import { readBooleanEnv } from './env'

type ReverbScheme = 'http' | 'https'

function isBrowser(): boolean {
  return typeof window !== 'undefined'
}

export function resolveScheme(): ReverbScheme {
  const envScheme = (import.meta as any).env?.VITE_REVERB_SCHEME

  if (typeof envScheme === 'string' && envScheme.trim().length > 0) {
    const scheme = envScheme.toLowerCase().trim()
    if (scheme === 'https' || scheme === 'http') {
      return scheme as ReverbScheme
    }
  }

  if (isBrowser()) {
    const protocol = window.location.protocol
    if (protocol === 'https:') {
      return 'https'
    }
  }

  return 'http'
}

export function resolveHost(): string | undefined {
  const envHost = (import.meta as any).env?.VITE_REVERB_HOST
  if (typeof envHost === 'string' && envHost.trim().length > 0) {
    return envHost.trim()
  }
  if (isBrowser()) {
    return window.location.hostname
  }
  return undefined
}

export function resolvePort(scheme: ReverbScheme): number | undefined {
  const isDev = (import.meta as any).env?.DEV === true ||
                (import.meta as any).env?.MODE === 'development' ||
                (typeof (import.meta as any).env?.DEV !== 'undefined' && (import.meta as any).env?.DEV)
  const envPort = (import.meta as any).env?.VITE_REVERB_PORT

  if (isBrowser() && window.location.port) {
    const pagePort = Number(window.location.port)
    if (!Number.isNaN(pagePort) && pagePort !== 6001) {
      const useProxyPort = readBooleanEnv('VITE_REVERB_USE_PROXY_PORT', isDev)

      if (useProxyPort) {
        logger.info('[echoClient] Using page port for nginx proxy', {
          pagePort,
          isDev,
          envPort: typeof envPort === 'string' ? envPort : 'not set',
          scheme,
          reason: isDev ? 'dev mode (auto)' : 'VITE_REVERB_USE_PROXY_PORT enabled',
          windowPort: window.location.port,
          windowHost: window.location.hostname,
        })
        return pagePort
      }
    }
  }

  if (typeof envPort === 'string' && envPort.trim().length > 0) {
    const parsed = Number(envPort)
    if (!Number.isNaN(parsed)) {
      logger.debug('[echoClient] Using port from VITE_REVERB_PORT env', {
        port: parsed,
        scheme,
      })
      return parsed
    }
  }

  logger.debug('[echoClient] Using default port 6001', {
    scheme,
    isDev,
  })
  return 6001
}

function resolvePath(): string | undefined {
  const envPath =
    (import.meta as any).env?.VITE_REVERB_SERVER_PATH ??
    (import.meta as any).env?.VITE_REVERB_PATH

  if (typeof envPath === 'string' && envPath.trim().length > 0) {
    const trimmed = envPath.trim()
    return trimmed.startsWith('/') ? trimmed : `/${trimmed}`
  }

  return undefined
}

export function buildEchoConfig(): Record<string, unknown> {
  const isDev = (import.meta as any).env?.DEV === true
  const scheme = resolveScheme()
  const host = resolveHost()
  const port = resolvePort(scheme)
  const path = resolvePath()

  let shouldUseTls = false
  if (scheme === 'https') {
    shouldUseTls = true
  } else if (isBrowser() && window.location.protocol === 'https:') {
    shouldUseTls = true
    logger.warn('[echoClient] Page is HTTPS but scheme is HTTP, forcing TLS', {
      scheme,
      protocol: window.location.protocol,
    })
  }

  if (isDev && isBrowser() && window.location.protocol === 'https:') {
    shouldUseTls = true
    logger.debug('[echoClient] Dev mode with HTTPS page, forcing TLS to avoid mixed content', {
      scheme,
      protocol: window.location.protocol,
    })
  }

  const forceTls = readBooleanEnv('VITE_WS_TLS', shouldUseTls)

  const key =
    (import.meta as any).env?.VITE_REVERB_APP_KEY ||
    (import.meta as any).env?.VITE_PUSHER_APP_KEY ||
    'local'

  const csrfToken = isBrowser()
    ? document.querySelector('meta[name="csrf-token"]')?.getAttribute('content')
    : undefined

  const enabledTransports = isDev && forceTls
    ? ['ws', 'wss']
    : forceTls
      ? ['wss']
      : ['ws']

  logger.debug('[echoClient] Building Echo config', {
    scheme,
    host,
    port,
    path,
    pathType: typeof path,
    pathIsUndefined: path === undefined,
    forceTls,
    isDev,
    pageProtocol: isBrowser() ? window.location.protocol : 'unknown',
    enabledTransports,
  })

  const echoConfig: Record<string, unknown> = {
    broadcaster: 'reverb',
    key,
    wsHost: host,
    wsPort: port,
    wssPort: port,
    forceTLS: forceTls,
    enabledTransports,
    disableStats: true,
    withCredentials: true,
    authEndpoint: '/broadcasting/auth',
    auth: {
      headers: {
        'X-Requested-With': 'XMLHttpRequest',
        ...(csrfToken ? { 'X-CSRF-TOKEN': csrfToken } : {}),
      },
      withCredentials: true,
    },
    encrypted: forceTls,
  }

  if (path) {
    if (path.includes('/app/app') || path.startsWith('/app/app/')) {
      logger.warn('[echoClient] wsPath contains double /app/app pattern', {
        wsPath: path,
        suggestion: 'Remove duplicate /app from path. Reverb listens on /app/{app_key}',
      })
    }
    echoConfig.wsPath = path
    logger.debug('[echoClient] wsPath set in config from environment', { wsPath: path })
  } else {
    logger.debug('[echoClient] wsPath not set, pusher-js will use default /app', {
      note: 'Reverb listens on /app/{app_key}, pusher-js defaults to /app',
    })
  }

  logger.debug('[echoClient] Final Echo config', {
    hasWsPath: 'wsPath' in echoConfig,
    wsPath: echoConfig.wsPath,
    key,
    wsHost: host,
    wsPort: port,
  })

  return echoConfig
}

