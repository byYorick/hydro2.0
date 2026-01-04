// Импортируем единый apiClient вместо настройки window.axios
// Вся конфигурация (CSRF, baseURL, interceptors) теперь в utils/apiClient.ts
import apiClient from './utils/apiClient';
import { logger } from './utils/logger';
import { initEcho, isEchoInitializing, getEchoInstance, onWsStateChange } from './utils/echoClient';
import Echo from 'laravel-echo';

if (typeof window !== 'undefined' && import.meta.env.DEV) {
  const existingPatch = (window.__boostFetchPatched === true)
  if (!existingPatch && typeof window.fetch === 'function') {
    window.__boostFetchPatched = true
    const originalFetch = window.fetch.bind(window)
    window.fetch = (input, init) => {
      const url = typeof input === 'string' ? input : input?.url ?? ''
      const isBoostLog = url.includes('/_boost/browser-logs')
      if (!isBoostLog) {
        return originalFetch(input, init)
      }
      return originalFetch(input, init).catch(() => {
        // Avoid noisy console errors from Boost logger during HMR/page swaps.
        return new Response(JSON.stringify({ status: 'ok' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      })
    }
  }
}

// Экспортируем apiClient в window.axios для обратной совместимости
// (если где-то в коде используется window.axios напрямую)
window.axios = apiClient;

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
let initializationScheduled = false;

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

// Упрощенная инициализация: однократный вызов initEcho
// Reconnect управляется исключительно через echoClient.ts
function initializeEchoOnLoad() {
  // Проверяем, не инициализирован ли Echo уже
  if (window.Echo) {
    const pusher = window.Echo.connector?.pusher;
    const connection = pusher?.connection;
    if (connection && (connection.state === 'connected' || connection.state === 'connecting')) {
      logger.debug('[bootstrap.js] Echo already initialized and active, skipping', {
        state: connection.state,
        socketId: connection.socket_id,
      });
      echoInitialized = true;
      return;
    }
  }
  
  if (echoInitialized || echoInitInProgress) {
    logger.debug('[bootstrap.js] Echo initialization already in progress or completed', {});
    return;
  }
  
  const attemptInit = () => {
    const echo = initializeEchoOnce();
    if (echo && window.Echo) {
      logger.info('[bootstrap.js] Echo initialized successfully', {
        socketId: echo.connector?.pusher?.connection?.socket_id,
      });
    } else {
      logger.warn('[bootstrap.js] Echo initialization returned null', {
        isInitializing: isEchoInitializing(),
        hasExistingInstance: !!getEchoInstance(),
        hasWindowEcho: !!window.Echo,
      });
      // Reconnect будет управляться через echoClient.ts, не делаем retry здесь
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
// Обработчик события reconciliation для синхронизации данных при переподключении
window.addEventListener('ws:reconciliation', (event) => {
  const detail = event.detail || {}
  
  // Валидация reconciliation данных
  import('./types/reconciliation').then(({ isValidReconciliationData }) => {
    if (!isValidReconciliationData(detail)) {
      logger.warn('[bootstrap.js] Invalid reconciliation data received', {
        detail,
      })
      return
    }
    
    const { telemetry, commands, alerts } = detail
    
    logger.info('[bootstrap.js] Processing reconciliation data', {
      telemetryCount: telemetry?.length || 0,
      commandsCount: commands?.length || 0,
      alertsCount: alerts?.length || 0,
    })

  // Обновляем алерты через store
  if (alerts && Array.isArray(alerts)) {
    try {
      // Динамически импортируем store, чтобы избежать циклических зависимостей
      import('./stores/alerts').then(({ useAlertsStore }) => {
        const alertsStore = useAlertsStore()
        // Обновляем только активные алерты из snapshot
        const activeAlerts = alerts.filter((a) => a.status === 'ACTIVE' || a.status === 'active')
        alertsStore.setAll(activeAlerts)
        logger.debug('[bootstrap.js] Alerts updated from reconciliation', {
          count: activeAlerts.length,
        })
      }).catch((err) => {
        logger.warn('[bootstrap.js] Failed to update alerts from reconciliation', {
          error: err instanceof Error ? err.message : String(err),
        })
      })
    } catch (err) {
      logger.warn('[bootstrap.js] Error processing alerts reconciliation', {
        error: err instanceof Error ? err.message : String(err),
      })
    }
  }

  // Уведомляем composables о необходимости обновления телеметрии и команд
  // Они сами решат, нужно ли обновлять данные на основе текущего состояния
  if (typeof window !== 'undefined' && window.dispatchEvent) {
    // Создаем отдельные события для каждого типа данных
    if (telemetry && Array.isArray(telemetry)) {
      window.dispatchEvent(new CustomEvent('ws:reconciliation:telemetry', {
        detail: { telemetry },
      }))
    }
    if (commands && Array.isArray(commands)) {
      window.dispatchEvent(new CustomEvent('ws:reconciliation:commands', {
        detail: { commands },
      }))
    }
    }
  }).catch((err) => {
    logger.error('[bootstrap.js] Error validating reconciliation data', {
      error: err instanceof Error ? err.message : String(err),
    })
  })
})

window.addEventListener('echo:teardown', () => {
  logger.debug('[bootstrap.js] Echo teardown event received, resetting flags', {});
  echoInitialized = false;
  echoInitInProgress = false;
});

// Инициализируем Echo после полной загрузки DOM (один раз)
// Reconnect управляется исключительно через echoClient.ts
initializeEchoOnLoad();

// Подписки на WebSocket каналы (зоны, алерты) перенесены в ws/subscriptions.ts
// Используйте: import { subscribeZone, subscribeAlerts } from '@/ws/subscriptions'

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
  logger.info('[bootstrap.js] Page restored from back/forward cache', {
    persisted: event.persisted,
  });
  
  // Сбрасываем флаги, но не инициализируем Echo
  // Reconnect управляется через echoClient.ts
  echoInitialized = false;
  echoInitInProgress = false;
};

const visibilityChangeHandler = () => {
  if (document.hidden) {
    return;
  }
  
  logger.debug('[bootstrap.js] Page visible', {});
  
  // Не делаем reconnect - echoClient.ts управляет этим автоматически
  // Просто логируем для отладки
  if (window.Echo) {
    const pusher = window.Echo.connector?.pusher;
    const connection = pusher?.connection;
    const state = connection?.state;
    logger.debug('[bootstrap.js] WebSocket state on visibility change', {
      state,
      socketId: connection?.socket_id,
    });
  }
};

const focusHandler = () => {
  // Не делаем reconnect - echoClient.ts управляет этим автоматически
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
