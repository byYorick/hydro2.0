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
    console.error('[HTTP ERROR]', method, url, { status, data, error });
    return Promise.reject(error);
  }
);

// ИСПРАВЛЕНО: Удалены локальные флаги - теперь используется единая точка входа в echoClient.ts
// Флаги isInitializing и initializationPromise управляются в echoClient.ts

// ИСПРАВЛЕНО: ЕДИНАЯ ТОЧКА ВХОДА для инициализации WebSocket
// Все инициализации проходят через initEcho() из echoClient.ts
// Эта функция является оберткой для удобства использования в bootstrap.js
function initializeEcho() {
  // Проверяем, не идет ли уже инициализация через echoClient
  if (isEchoInitializing()) {
    logger.debug('[bootstrap.js] Echo initialization already in progress via echoClient, skipping', {});
    return;
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
      return;
    }
  }
  
  try {
    // ИСПРАВЛЕНО: Используем единую точку входа initEcho()
    // forceReinit = true для гарантии чистой инициализации при загрузке страницы
    const echo = initEcho(true);
    if (echo) {
      logger.info('[bootstrap.js] Echo client initialized via single entry point', {
        socketId: echo.connector?.pusher?.connection?.socket_id,
      });
    } else {
      logger.warn('[bootstrap.js] Echo client initialization returned null', {
        isInitializing: isEchoInitializing(),
        hasExistingInstance: !!getEchoInstance(),
      });
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
  }
}

// Инициализируем Echo после полной загрузки DOM
if (document.readyState === 'loading') {
  // DOM еще загружается, ждем события DOMContentLoaded
  document.addEventListener('DOMContentLoaded', () => {
    // Небольшая задержка для гарантии, что все скрипты загружены
    setTimeout(initializeEcho, 100);
  });
} else {
  // DOM уже загружен, инициализируем сразу с небольшой задержкой
  setTimeout(initializeEcho, 100);
}

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

// ИСПРАВЛЕНО: Обработка глобальных ошибок без перезагрузки страницы
window.addEventListener('error', (event) => {
  // ИСПРАВЛЕНО: Логируем ошибку, но НЕ перезагружаем страницу
  // eslint-disable-next-line no-console
  console.error('[WINDOW ERROR]', event?.message, event?.error);
  // Предотвращаем стандартное поведение браузера (перезагрузку страницы)
  event.preventDefault();
  // НЕ вызываем location.reload() или router.reload() здесь
});

window.addEventListener('unhandledrejection', (event) => {
  // Игнорируем отмененные запросы Inertia.js
  const reason = event?.reason;
  if (reason?.code === 'ERR_CANCELED' || reason?.name === 'CanceledError' || reason?.message === 'canceled') {
    // Не логируем отмененные запросы
    event.preventDefault();
    return;
  }
  // ИСПРАВЛЕНО: Логируем ошибку, но НЕ перезагружаем страницу
  // eslint-disable-next-line no-console
  console.error('[UNHANDLED REJECTION]', reason || event);
  // Предотвращаем стандартное поведение браузера
  event.preventDefault();
  // НЕ вызываем location.reload() или router.reload() здесь
});

// ИСПРАВЛЕНО: Очистка WebSocket соединения при перезагрузке страницы
// Это предотвращает проблемы с "висящими" соединениями при жесткой перезагрузке
window.addEventListener('beforeunload', () => {
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
});

// Также очищаем при событии pagehide (более надежно для мобильных браузеров)
window.addEventListener('pagehide', () => {
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
});

// ИСПРАВЛЕНО: Переподключение при возврате на страницу из back/forward cache и жесткой перезагрузке
// При жесткой перезагрузке страница может быть восстановлена из кеша браузера
// В этом случае нужно проверить состояние соединения и переподключиться, если необходимо
window.addEventListener('pageshow', (event) => {
  // event.persisted = true означает, что страница была восстановлена из bfcache
  if (event.persisted) {
    logger.info('[bootstrap.js] Page restored from back/forward cache, checking WebSocket connection', {
      persisted: event.persisted,
    });
    
    // Проверяем состояние соединения и переподключаемся, если необходимо
    setTimeout(() => {
      const echo = window.Echo;
      if (echo && echo.connector?.pusher) {
        const connection = echo.connector.pusher.connection;
        const state = connection?.state;
        
        logger.debug('[bootstrap.js] WebSocket state after page restore', {
          state,
          socketId: connection?.socket_id,
        });
        
        // Если соединение не активно, переинициализируем
        if (state !== 'connected' && state !== 'connecting') {
          logger.info('[bootstrap.js] WebSocket not connected after page restore, reinitializing', {
            state,
          });
          initializeEcho();
        }
      } else {
        // Если Echo не инициализирован, инициализируем
        logger.info('[bootstrap.js] Echo not initialized after page restore, initializing', {});
        initializeEcho();
      }
    }, 200); // Небольшая задержка для стабилизации
  } else {
    // Обычная загрузка страницы или жесткая перезагрузка
    // ИСПРАВЛЕНО: Улучшена проверка состояния после загрузки с несколькими попытками
    // Это критично для жесткой перезагрузки, когда соединение может не успеть установиться
    const checkConnection = (attempt = 0) => {
      const maxAttempts = 5 // 5 попыток проверки
      const delays = [500, 1000, 2000, 3000, 5000] // Увеличивающиеся задержки
      const delay = delays[Math.min(attempt, delays.length - 1)]
      
      setTimeout(() => {
        const echo = window.Echo;
        if (echo && echo.connector?.pusher) {
          const connection = echo.connector.pusher.connection;
          const state = connection?.state;
          
          logger.debug('[bootstrap.js] Checking WebSocket connection state after page load', {
            attempt: attempt + 1,
            maxAttempts,
            state,
            socketId: connection?.socket_id,
          });
          
          if (state === 'connected' || state === 'connecting') {
            logger.info('[bootstrap.js] WebSocket connection established', {
              state,
              socketId: connection?.socket_id,
              attempts: attempt + 1,
            });
            return // Соединение установлено, выходим
          }
          
          // Если соединение не установлено и не в процессе подключения
          if (state !== 'connected' && state !== 'connecting') {
            if (attempt < maxAttempts - 1) {
              // Продолжаем проверку
              logger.debug('[bootstrap.js] Connection not ready, will retry', {
                state,
                attempt: attempt + 1,
                nextDelay: delays[Math.min(attempt + 1, delays.length - 1)],
              });
              checkConnection(attempt + 1)
            } else {
              // Все попытки исчерпаны, переинициализируем
              logger.warn('[bootstrap.js] WebSocket not connected after all checks, reinitializing', {
                state,
                socketId: connection?.socket_id,
                attempts: maxAttempts,
              });
              initializeEcho();
            }
          }
        } else {
          // Echo не инициализирован
          if (attempt < maxAttempts - 1) {
            logger.debug('[bootstrap.js] Echo not initialized yet, will retry', {
              attempt: attempt + 1,
              nextDelay: delays[Math.min(attempt + 1, delays.length - 1)],
            });
            checkConnection(attempt + 1)
          } else {
            logger.warn('[bootstrap.js] Echo not initialized after all checks, initializing', {
              attempts: maxAttempts,
            });
            initializeEcho();
          }
        }
      }, delay)
    }
    
    // Начинаем проверку с первой попытки
    checkConnection(0)
  }
});
