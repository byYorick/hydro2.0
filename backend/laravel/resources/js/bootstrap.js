import axios from 'axios';
window.axios = axios;

window.axios.defaults.headers.common['X-Requested-With'] = 'XMLHttpRequest';

// Настройка axios для работы с Laravel сессиями и CSRF
axios.defaults.withCredentials = true;
axios.defaults.headers.common['Accept'] = 'application/json';

// Получить CSRF токен из meta тега или cookie
const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
if (csrfToken) {
  axios.defaults.headers.common['X-CSRF-TOKEN'] = csrfToken;
}

import { logger } from './utils/logger';
import { initEcho, isEchoInitializing, getEchoInstance } from './utils/echoClient';
import Echo from 'laravel-echo';

// Axios error logging to console
window.axios.interceptors.response.use(
  (res) => res,
  (error) => {
    // Игнорируем отмененные запросы (CanceledError) - это нормальное поведение Inertia.js
    // при быстром переключении между страницами
    if (error?.code === 'ERR_CANCELED' || error?.name === 'CanceledError' || error?.message === 'canceled') {
      // Не логируем отмененные запросы - это нормальное поведение
      return Promise.reject(error);
    }
    
    // Network or API errors
    const cfg = error?.config || {};
    const url = cfg.url || '(unknown url)';
    const method = (cfg.method || 'GET').toUpperCase();
    const status = error?.response?.status;
    const data = error?.response?.data;
    
    // Логируем только реальные ошибки
    // eslint-disable-next-line no-console
    logger.error('[HTTP ERROR]', { method, url, status, data, error });
    return Promise.reject(error);
  }
);

function initializeEcho() {
  if (isEchoInitializing()) {
    logger.debug('[bootstrap.js] Echo initialization already in progress via echoClient, skipping', {});
    return null;
  }
  
  // HMR guard: проверяем существующий window.Echo перед проверкой getEchoInstance()
  // При HMR модуль перезагружается, но window.Echo остается живым
  let existingWindowEcho = window.Echo;
  let existingEcho = getEchoInstance();
  
  // Если window.Echo существует, но getEchoInstance() возвращает null (HMR case),
  // проверяем состояние window.Echo и решаем, что делать
  if (existingWindowEcho && !existingEcho) {
    const pusher = existingWindowEcho.connector?.pusher;
    const connection = pusher?.connection;
    const state = connection?.state;
    
    if (state === 'connected' || state === 'connecting') {
      // Активное соединение - переиспользуем window.Echo
      logger.info('[bootstrap.js] HMR detected: reusing existing active window.Echo', {
        state: state,
        socketId: connection?.socket_id,
      });
      // Синхронизируем флаги с реальным состоянием
      echoInitialized = true;
      echoInitInProgress = false;
      return existingWindowEcho;
    } else {
      // Неактивное соединение - нужно teardown перед новой инициализацией
      logger.info('[bootstrap.js] HMR detected: existing window.Echo is inactive, tearing down', {
        state: state,
      });
      try {
        // Вызываем teardown для существующего Echo
        if (pusher && typeof pusher.disconnect === 'function') {
          pusher.disconnect();
        }
        if (connection && typeof connection.disconnect === 'function') {
          connection.disconnect();
        }
        // Очищаем window.Echo
        window.Echo = undefined;
        existingWindowEcho = undefined;
      } catch (err) {
        logger.warn('[bootstrap.js] Error tearing down existing Echo during HMR', {
          error: err instanceof Error ? err.message : String(err),
        });
        // Продолжаем с принудительной переинициализацией
        window.Echo = undefined;
        existingWindowEcho = undefined;
      }
    }
  }
  
  // Проверяем существующий Echo из модуля (нормальный случай, не HMR)
  if (existingEcho && window.Echo) {
    const pusher = existingEcho.connector?.pusher;
    const connection = pusher?.connection;
    if (connection && (connection.state === 'connected' || connection.state === 'connecting')) {
      logger.debug('[bootstrap.js] Echo already initialized and connected, skipping', {
        state: connection.state,
        socketId: connection.socket_id,
      });
      return existingEcho;
    }
  }
  
  try {
    // Принудительная переинициализация нужна, если есть старый Echo (неактивный)
    const shouldForceReinit = !!(existingEcho || existingWindowEcho) && !!window.Echo;
    const echo = initEcho(shouldForceReinit);
    if (echo) {
      logger.info('[bootstrap.js] Echo client initialized via single entry point', {
        socketId: echo.connector?.pusher?.connection?.socket_id,
        forceReinit: shouldForceReinit,
      });
      return echo;
    } else {
      logger.warn('[bootstrap.js] Echo client initialization returned null', {
        isInitializing: isEchoInitializing(),
        hasExistingInstance: !!getEchoInstance(),
        hasWindowEcho: !!window.Echo,
      });
      return null;
    }
  } catch (e) {
    let errorMessage = 'Unknown error';
    let errorType = typeof e;
    
    if (e instanceof Error) {
      errorMessage = e.message || String(e);
      errorType = e.name || 'Error';
    } else if (typeof e === 'string') {
      errorMessage = e;
    } else if (e && typeof e === 'object' && 'message' in e) {
      errorMessage = String(e.message);
    } else {
      errorMessage = String(e);
    }
    
    logger.error('[bootstrap.js] Ошибка инициализации Echo', {
      error: errorMessage,
      errorType: errorType,
      errorValue: e,
    }, e instanceof Error ? e : undefined);
    window.Echo = undefined;
    return null;
  }
}

// Инициализируем Echo только один раз при загрузке страницы
// Добавляем защиту от множественных инициализаций
let echoInitialized = false;
let echoInitInProgress = false;

function initializeEchoOnce() {
  if (echoInitialized || echoInitInProgress) {
    logger.debug('[bootstrap.js] Echo already initialized or in progress, skipping', {
      initialized: echoInitialized,
      inProgress: echoInitInProgress,
    });
    return window.Echo || null;
  }
  echoInitInProgress = true;
  try {
    const echo = initializeEcho();
    if (echo && window.Echo) {
      const pusher = echo.connector?.pusher;
      const connection = pusher?.connection;
      echoInitialized = true;
      logger.debug('[bootstrap.js] Echo initialized successfully', {
        hasConnection: !!connection,
        connectionState: connection?.state,
      });
      return echo;
    } else {
      logger.warn('[bootstrap.js] Echo initialization returned null or window.Echo not set', {
        echoReturned: !!echo,
        windowEcho: !!window.Echo,
      });
      echoInitialized = false;
      return null;
    }
  } catch (error) {
    logger.error('[bootstrap.js] Error initializing Echo', {
      error: error instanceof Error ? error.message : String(error),
    });
    echoInitialized = false;
    return null;
  } finally {
    echoInitInProgress = false;
  }
}

let initializationScheduled = false;
let initializationAttempts = 0;
const MAX_INIT_ATTEMPTS = 5;
const INIT_RETRY_DELAYS = [1000, 2000, 5000, 10000, 30000];

function scheduleEchoInitialization(force = false) {
  if (initializationScheduled && !force) {
    logger.debug('[bootstrap.js] Echo initialization already scheduled, skipping', {});
    return;
  }
  
  if (force) {
    initializationScheduled = false;
    initializationAttempts = 0;
  }
  
  if (initializationScheduled) {
    return;
  }
  
  initializationScheduled = true;
  
  const attemptInit = () => {
    // Проверяем реальное состояние соединения, а не только флаг
    if (window.Echo) {
      const pusher = window.Echo.connector?.pusher;
      const connection = pusher?.connection;
      if (connection && (connection.state === 'connected' || connection.state === 'connecting')) {
        logger.debug('[bootstrap.js] Echo already connected or connecting, skipping initialization', {
          state: connection.state,
          socketId: connection.socket_id,
        });
        initializationScheduled = false;
        echoInitialized = true;
        return;
      }
    }
    
    if (echoInitialized || echoInitInProgress) {
      initializationScheduled = false;
      return;
    }
    
    const echo = initializeEchoOnce();
    
    if (!echo || !window.Echo) {
      initializationAttempts++;
      
      if (initializationAttempts < MAX_INIT_ATTEMPTS) {
        const delay = INIT_RETRY_DELAYS[initializationAttempts - 1] || 30000;
        logger.debug('[bootstrap.js] Echo initialization failed, retrying', {
          attempt: initializationAttempts,
          maxAttempts: MAX_INIT_ATTEMPTS,
          nextRetryIn: delay,
        });
        
        initializationScheduled = false;
        setTimeout(() => {
          scheduleEchoInitialization();
        }, delay);
      } else {
        logger.error('[bootstrap.js] Echo initialization failed after max attempts', {
          attempts: initializationAttempts,
        });
        initializationScheduled = false;
      }
    } else {
      initializationAttempts = 0;
      initializationScheduled = false;
    }
  };
  
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      setTimeout(attemptInit, 100);
    }, { once: true });
  } else {
    setTimeout(attemptInit, 100);
  }
}

// Обработчик события teardown от echoClient.ts
window.addEventListener('echo:teardown', () => {
  logger.debug('[bootstrap.js] Echo teardown event received, resetting flags', {});
  echoInitialized = false;
  echoInitInProgress = false;
  initializationScheduled = false;
  initializationAttempts = 0;
});

// Инициализируем Echo после полной загрузки DOM
scheduleEchoInitialization();

// Zones WS subscription helper (example)
export function subscribeZone(zoneId, handler) {
  if (!window.Echo) return () => {}
  const channel = window.Echo.private(`hydro.zones.${zoneId}`)
  channel.listen('.App\\Events\\ZoneUpdated', (e) => {
    handler?.(e)
  })
  // Возвращаем функцию для отписки
  return () => {
    if (channel) {
      channel.stopListening('.App\\Events\\ZoneUpdated')
    }
  }
}

export function subscribeAlerts(handler) {
  if (!window.Echo) {
    logger.warn('[bootstrap.js] Echo not available, skip subscribeAlerts', {})
    return () => {}
  }

  const channelName = 'hydro.alerts'
  const eventName = '.App\\Events\\AlertCreated'
  const channel = window.Echo.private(channelName)
  const listener = (event) => handler?.(event)

  channel.listen(eventName, listener)

  return () => {
    try {
      channel.stopListening(eventName)
      if (typeof window.Echo?.leave === 'function') {
        window.Echo.leave(channelName)
      }
    } catch (error) {
      logger.warn('[bootstrap.js] subscribeAlerts cleanup failed', { error })
    }
  }
}

// Обработка глобальных ошибок с логированием, но без блокировки стандартного поведения
// Сохраняем ссылки на обработчики в глобальной области для очистки при HMR
// НЕ вызываем event.preventDefault() - это глушит ошибки и мешает Vite/Sentry/консоли

// Глобальное хранилище обработчиков для HMR очистки
if (typeof window !== 'undefined' && !window.__bootstrapHandlers) {
  window.__bootstrapHandlers = {
    error: null,
    unhandledrejection: null,
    beforeunload: null,
    pagehide: null,
    pageshow: null,
    visibilitychange: null,
    focus: null,
  }
}

const errorHandler = (event) => {
  // Логируем ошибку для нашего логгера, но позволяем стандартному поведению работать
  // Это позволяет Vite HMR, Sentry и консоли браузера нормально обрабатывать ошибки
  import('./utils/logger').then(({ logger }) => {
      logger.error('[WINDOW ERROR]', { message: event?.message, error: event?.error });
  }).catch(() => {
      // Игнорируем ошибки при логировании, чтобы не создавать цикл
  });
  // НЕ вызываем event.preventDefault() - ошибки должны всплывать нормально
  // Это критично для работы Vite HMR, Sentry и отладки в консоли браузера
};

const unhandledRejectionHandler = (event) => {
  // Игнорируем отмененные запросы Inertia.js
  const reason = event?.reason;
  if (reason?.code === 'ERR_CANCELED' || reason?.name === 'CanceledError' || reason?.message === 'canceled') {
    // Не логируем отмененные запросы - это нормальное поведение Inertia.js
    // НЕ вызываем event.preventDefault() даже для отмененных запросов
    // Это позволяет браузеру нормально обрабатывать все события
    return;
  }
  // Логируем ошибку для нашего логгера, но позволяем стандартному поведению работать
  // Это позволяет Vite HMR, Sentry и консоли браузера нормально обрабатывать ошибки
  import('./utils/logger').then(({ logger }) => {
      logger.error('[UNHANDLED REJECTION]', { reason: reason || event });
  }).catch(() => {
      // Игнорируем ошибки при логировании, чтобы не создавать цикл
  });
  // НЕ вызываем event.preventDefault() - ошибки должны всплывать нормально
  // Это критично для работы Vite HMR, Sentry и отладки в консоли браузера
};

const beforeUnloadHandler = () => {
  if (window.Echo && window.Echo.connector?.pusher) {
    try {
      const pusher = window.Echo.connector.pusher;
      // Отключаем соединение перед перезагрузкой страницы
      if (typeof pusher.disconnect === 'function') {
        pusher.disconnect();
      } else if (pusher.connection && typeof pusher.connection.disconnect === 'function') {
        pusher.connection.disconnect();
      }
      logger.debug('[bootstrap.js] WebSocket disconnected before page unload', {});
    } catch (err) {
      // Игнорируем ошибки при отключении (страница уже перезагружается)
      logger.debug('[bootstrap.js] Error disconnecting WebSocket before unload (ignored)', {
        error: err instanceof Error ? err.message : String(err),
      });
    }
  }
};

const pagehideHandler = (event) => {
  if (event.persisted) {
    return;
  }
  
  if (window.Echo && window.Echo.connector?.pusher) {
    try {
      const pusher = window.Echo.connector.pusher;
      const connection = pusher.connection;
      
      if (connection && connection.state === 'connected') {
        logger.debug('[bootstrap.js] Page hidden, keeping connection alive', {});
        return;
      }
    } catch (err) {
      logger.debug('[bootstrap.js] Error checking connection state on pagehide', {
        error: err instanceof Error ? err.message : String(err),
      });
    }
  }
};

const pageshowHandler = (event) => {
  if (!event.persisted) {
    return;
  }
  logger.info('[bootstrap.js] Page restored from back/forward cache, checking WebSocket connection', {
    persisted: event.persisted,
  });
  
  echoInitialized = false;
  echoInitInProgress = false;
  initializationScheduled = false;
  
  setTimeout(() => {
    const echo = window.Echo;
    if (echo && echo.connector?.pusher) {
      const connection = echo.connector.pusher.connection;
      const state = connection?.state;
      
      if (state !== 'connected' && state !== 'connecting') {
        initializeEchoOnce();
      }
    } else if (!echo) {
      initializeEchoOnce();
    }
  }, 200);
};

const visibilityChangeHandler = () => {
  if (document.hidden) {
    return;
  }
  
  logger.debug('[bootstrap.js] Page visible, checking WebSocket connection', {});
  
  setTimeout(() => {
    const echo = window.Echo;
    if (!echo) {
      logger.info('[bootstrap.js] Echo not initialized after visibility change, initializing', {});
      scheduleEchoInitialization(true);
      return;
    }
    
    const pusher = echo.connector?.pusher;
    const connection = pusher?.connection;
    const state = connection?.state;
    
    if (state !== 'connected' && state !== 'connecting') {
      logger.info('[bootstrap.js] WebSocket not connected after visibility change, reconnecting', {
        state,
      });
      
      try {
        if (pusher && typeof pusher.connect === 'function') {
          pusher.connect();
        } else if (connection && typeof connection.connect === 'function') {
          connection.connect();
        } else {
          scheduleEchoInitialization(true);
        }
      } catch (err) {
        logger.warn('[bootstrap.js] Error reconnecting on visibility change', {
          error: err instanceof Error ? err.message : String(err),
        });
        scheduleEchoInitialization(true);
      }
    }
  }, 200);
};

const focusHandler = () => {
  visibilityChangeHandler();
};

// Функция для очистки всех обработчиков
function cleanupBootstrapHandlers() {
  if (typeof window === 'undefined' || !window.__bootstrapHandlers) {
    return
  }
  
  const handlers = window.__bootstrapHandlers
  
  if (handlers.error) {
    window.removeEventListener('error', handlers.error)
    handlers.error = null
  }
  if (handlers.unhandledrejection) {
    window.removeEventListener('unhandledrejection', handlers.unhandledrejection)
    handlers.unhandledrejection = null
  }
  if (handlers.beforeunload) {
    window.removeEventListener('beforeunload', handlers.beforeunload)
    handlers.beforeunload = null
  }
  if (handlers.pagehide) {
    window.removeEventListener('pagehide', handlers.pagehide)
    handlers.pagehide = null
  }
  if (handlers.pageshow) {
    window.removeEventListener('pageshow', handlers.pageshow)
    handlers.pageshow = null
  }
  if (handlers.visibilitychange) {
    document.removeEventListener('visibilitychange', handlers.visibilitychange)
    handlers.visibilitychange = null
  }
  if (handlers.focus) {
    window.removeEventListener('focus', handlers.focus)
    handlers.focus = null
  }
}

// Очищаем старые обработчики перед добавлением новых
cleanupBootstrapHandlers()

// Сохраняем ссылки на обработчики в глобальном хранилище
if (typeof window !== 'undefined' && window.__bootstrapHandlers) {
  window.__bootstrapHandlers.error = errorHandler
  window.__bootstrapHandlers.unhandledrejection = unhandledRejectionHandler
  window.__bootstrapHandlers.beforeunload = beforeUnloadHandler
  window.__bootstrapHandlers.pagehide = pagehideHandler
  window.__bootstrapHandlers.pageshow = pageshowHandler
  window.__bootstrapHandlers.visibilitychange = visibilityChangeHandler
  window.__bootstrapHandlers.focus = focusHandler
}

// Добавляем обработчики
window.addEventListener('error', errorHandler)
window.addEventListener('unhandledrejection', unhandledRejectionHandler)
window.addEventListener('beforeunload', beforeUnloadHandler)
window.addEventListener('pagehide', pagehideHandler)
window.addEventListener('pageshow', pageshowHandler)
document.addEventListener('visibilitychange', visibilityChangeHandler)
window.addEventListener('focus', focusHandler)

// Очистка при HMR
if (import.meta.hot) {
  import.meta.hot.on('vite:beforeUpdate', () => {
    cleanupBootstrapHandlers()
    
    // HMR guard: проверяем существующий window.Echo перед обновлением
    if (window.Echo) {
      const pusher = window.Echo.connector?.pusher;
      const connection = pusher?.connection;
      const state = connection?.state;
      
      if (state === 'connected' || state === 'connecting') {
        // Активное соединение - сохраняем для переиспользования
        logger.debug('[bootstrap.js] HMR: preserving active window.Echo', {
          state: state,
          socketId: connection?.socket_id,
        });
        // Сбрасываем только модульные флаги, window.Echo остается
        echoInitialized = false;
        echoInitInProgress = false;
        initializationScheduled = false;
      } else {
        // Неактивное соединение - очищаем
        logger.debug('[bootstrap.js] HMR: cleaning up inactive window.Echo', {
          state: state,
        });
        try {
          if (pusher && typeof pusher.disconnect === 'function') {
            pusher.disconnect();
          }
          if (connection && typeof connection.disconnect === 'function') {
            connection.disconnect();
          }
        } catch (err) {
          logger.warn('[bootstrap.js] HMR: error disconnecting Echo', {
            error: err instanceof Error ? err.message : String(err),
          });
        }
        window.Echo = undefined;
        echoInitialized = false;
        echoInitInProgress = false;
        initializationScheduled = false;
      }
    }
  })
  
  import.meta.hot.dispose(() => {
    cleanupBootstrapHandlers()
  })
}
