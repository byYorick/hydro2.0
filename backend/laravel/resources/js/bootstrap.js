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
// Импортируем без расширения - Vite автоматически обработает TypeScript
import { initEcho, isEchoInitializing, getEchoInstance } from './utils/echoClient';

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

// Удалены локальные флаги - теперь используется единая точка входа в echoClient.ts
// Флаги isInitializing и initializationPromise управляются в echoClient.ts

// ЕДИНАЯ ТОЧКА ВХОДА для инициализации WebSocket
// Все инициализации проходят через initEcho() из echoClient.ts
// Эта функция является оберткой для удобства использования в bootstrap.js
function initializeEcho() {
  // Проверяем, не идет ли уже инициализация через echoClient
  if (isEchoInitializing()) {
    logger.debug('[bootstrap.js] Echo initialization already in progress via echoClient, skipping', {});
    return null;
  }
  
  // Проверяем, есть ли уже активный экземпляр
  const existingEcho = getEchoInstance();
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
    // Используем единую точку входа initEcho()
    // forceReinit = false при первой инициализации, true только если Echo уже существует
    const shouldForceReinit = !!existingEcho && !!window.Echo;
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
      });
      return null;
    }
  } catch (e) {
    // Обработка ошибок, которые могут быть не Error объектами
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
    return;
  }
  echoInitInProgress = true;
  try {
    const echo = initializeEcho();
    // Ставим echoInitialized=true только если initEcho() вернул реальный экземпляр
    // Проверяем также, что window.Echo установлен и соединение активно
    if (echo && window.Echo) {
      const pusher = echo.connector?.pusher;
      const connection = pusher?.connection;
      // Считаем успешной инициализацией только если есть экземпляр
      // Соединение может быть еще в процессе подключения, это нормально
      echoInitialized = true;
      logger.debug('[bootstrap.js] Echo initialized successfully', {
        hasConnection: !!connection,
        connectionState: connection?.state,
      });
    } else {
      logger.warn('[bootstrap.js] Echo initialization returned null or window.Echo not set', {
        echoReturned: !!echo,
        windowEcho: !!window.Echo,
      });
      echoInitialized = false; // Разрешаем повторную попытку
    }
  } catch (error) {
    logger.error('[bootstrap.js] Error initializing Echo', {
      error: error instanceof Error ? error.message : String(error),
    });
    echoInitialized = false; // Разрешаем повторную попытку при ошибке
  } finally {
    echoInitInProgress = false;
  }
}

// Инициализируем Echo только один раз при загрузке страницы
// Добавляем дополнительную защиту от множественных инициализаций
let initializationScheduled = false;

function scheduleEchoInitialization() {
  if (initializationScheduled) {
    logger.debug('[bootstrap.js] Echo initialization already scheduled, skipping', {});
    return;
  }
  initializationScheduled = true;
  
  if (document.readyState === 'loading') {
    // DOM еще загружается, ждем события DOMContentLoaded
    document.addEventListener('DOMContentLoaded', () => {
      // Небольшая задержка для гарантии, что все скрипты загружены
      setTimeout(() => {
        if (!echoInitialized && !echoInitInProgress) {
          initializeEchoOnce();
        }
      }, 100);
    }, { once: true }); // once: true предотвращает множественные вызовы
  } else {
    // DOM уже загружен, инициализируем сразу с небольшой задержкой
    setTimeout(() => {
      if (!echoInitialized && !echoInitInProgress) {
        initializeEchoOnce();
      }
    }, 100);
  }
}

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
// Сохраняем ссылки на обработчики для очистки при HMR
// НЕ вызываем event.preventDefault() - это глушит ошибки и мешает Vite/Sentry/консоли
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

const pagehideHandler = () => {
  if (window.Echo && window.Echo.connector?.pusher) {
    try {
      const pusher = window.Echo.connector.pusher;
      if (typeof pusher.disconnect === 'function') {
        pusher.disconnect();
      } else if (pusher.connection && typeof pusher.connection.disconnect === 'function') {
        pusher.connection.disconnect();
      }
    } catch (err) {
      // Игнорируем ошибки
    }
  }
};

// Переподключение только при восстановлении из back/forward cache
// Обычная загрузка страницы обрабатывается через scheduleEchoInitialization()
// Определяем pageshowHandler ДО использования в HMR обработчиках
const pageshowHandler = (event) => {
  // Обрабатываем только event.persisted === true (восстановление из bfcache)
  // При обычной загрузке страницы event.persisted === false, и мы не должны ничего делать
  if (!event.persisted) {
    // Обычная загрузка страницы - не делаем ничего, инициализация уже идет через scheduleEchoInitialization()
    return;
  }
  
  // Страница восстановлена из back/forward cache - проверяем и переинициализируем WebSocket
  logger.info('[bootstrap.js] Page restored from back/forward cache, checking WebSocket connection', {
    persisted: event.persisted,
  });
  
  // Сбрасываем флаги при восстановлении из bfcache
  echoInitialized = false;
  echoInitInProgress = false;
  initializationScheduled = false;
  
  setTimeout(() => {
    const echo = window.Echo;
    if (echo && echo.connector?.pusher) {
      const connection = echo.connector.pusher.connection;
      const state = connection?.state;
      
      logger.debug('[bootstrap.js] WebSocket state after page restore from cache', {
        state,
        socketId: connection?.socket_id,
      });
      
      // Если соединение не активно, переинициализируем
      if (state !== 'connected' && state !== 'connecting') {
        logger.info('[bootstrap.js] WebSocket not connected after page restore, reinitializing', {
          state,
        });
        initializeEchoOnce();
      }
    } else if (!echo) {
      // Если Echo не инициализирован, инициализируем
      logger.info('[bootstrap.js] Echo not initialized after page restore, initializing', {});
      initializeEchoOnce();
    }
  }, 200);
};

// Очищаем старые обработчики перед добавлением новых (для HMR)
// При HMR Vite перезагружает модуль, но старые обработчики остаются, что приводит к дублированию
// Используем Vite HMR API для правильной очистки
if (import.meta.hot) {
  // Сохраняем ссылки на все обработчики для последующего удаления
  const handlers = {
    error: errorHandler,
    unhandledrejection: unhandledRejectionHandler,
    beforeunload: beforeUnloadHandler,
    pagehide: pagehideHandler,
    pageshow: pageshowHandler,
  }
  
  // Удаляем старые обработчики перед добавлением новых
  // Это предотвращает дублирование при HMR
  window.removeEventListener('error', handlers.error);
  window.removeEventListener('unhandledrejection', handlers.unhandledrejection);
  window.removeEventListener('beforeunload', handlers.beforeunload);
  window.removeEventListener('pagehide', handlers.pagehide);
  window.removeEventListener('pageshow', handlers.pageshow);
  
  // Используем Vite HMR API для очистки при горячей перезагрузке
  import.meta.hot.on('vite:beforeUpdate', () => {
    // Перед обновлением модуля удаляем все обработчики
    window.removeEventListener('error', handlers.error);
    window.removeEventListener('unhandledrejection', handlers.unhandledrejection);
    window.removeEventListener('beforeunload', handlers.beforeunload);
    window.removeEventListener('pagehide', handlers.pagehide);
    window.removeEventListener('pageshow', handlers.pageshow);
    logger.debug('[bootstrap.js] HMR: Removed all event handlers before update', {});
  })
  
  import.meta.hot.on('vite:afterUpdate', () => {
    // После обновления модуль будет перезагружен, обработчики добавятся заново
    logger.debug('[bootstrap.js] HMR: Module updated, handlers will be re-added', {});
  })
}

// Добавляем все обработчики после проверки HMR
// Это гарантирует, что обработчики добавлены только один раз
window.addEventListener('error', errorHandler);
window.addEventListener('unhandledrejection', unhandledRejectionHandler);
window.addEventListener('beforeunload', beforeUnloadHandler);
window.addEventListener('pagehide', pagehideHandler);
window.addEventListener('pageshow', pageshowHandler);
