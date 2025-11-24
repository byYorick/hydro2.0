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

// Laravel Echo (Reverb/Pusher-compatible)
import Echo from 'laravel-echo';
import Pusher from 'pusher-js';
window.Pusher = Pusher;

// Поддержка как Reverb, так и Pusher переменных для совместимости
const wsHost = import.meta.env.VITE_REVERB_HOST || import.meta.env.VITE_WS_HOST || window.location.hostname;
const wsPort = Number(import.meta.env.VITE_REVERB_PORT || import.meta.env.VITE_WS_PORT || 6001);
const useTLS = String(import.meta.env.VITE_REVERB_SCHEME || import.meta.env.VITE_WS_TLS || 'false') === 'true' || 
               String(import.meta.env.VITE_REVERB_SCHEME || 'http') === 'https';
const cluster = import.meta.env.VITE_PUSHER_APP_CLUSTER || 'mt1';
// Поддержка как REVERB, так и PUSHER ключей
const appKey = import.meta.env.VITE_REVERB_APP_KEY || import.meta.env.VITE_PUSHER_APP_KEY;
const wsEnabled = String(import.meta.env.VITE_ENABLE_WS || 'true') === 'true';

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

try {
  if (wsEnabled && appKey) {
    console.log('[bootstrap.js] Инициализация Echo:', { wsHost, wsPort, appKey: appKey ? '***' : 'missing', useTLS });
    window.Echo = new Echo({
      broadcaster: 'pusher',
      key: appKey,
      cluster,
      wsHost,
      wsPort,
      wssPort: wsPort,
      forceTLS: useTLS,
      disableStats: true,
      // Явно указываем только ws для dev режима, если не используется TLS
      enabledTransports: useTLS ? ['wss'] : ['ws'],
      // Дополнительные опции для Reverb
      authEndpoint: '/broadcasting/auth',
      auth: {
        headers: {
          'X-CSRF-TOKEN': csrfToken || '',
          'X-Requested-With': 'XMLHttpRequest',
        },
      },
      // Используем сессии для аутентификации
      withCredentials: true,
      // Дополнительные опции для отладки
      enabledLogging: true,
      // Настройки для улучшения стабильности соединения
      activityTimeout: 60000, // 60 секунд (увеличено для большей стабильности)
      pongTimeout: 30000, // 30 секунд
      unavailableTimeout: 10000, // 10 секунд перед попыткой переподключения
    });
    console.log('[bootstrap.js] Echo инициализирован успешно');
    
    // Настройка автоматической переподписки при reconnect
    // Функция для настройки обработчиков событий WebSocket
    let handlersSetup = false; // Флаг для предотвращения дублирования
    let currentConnectionState = null; // Отслеживаем состояние соединения
    
    const setupWebSocketHandlers = () => {
      const pusher = window.Echo?.connector?.pusher;
      if (!pusher?.connection) {
        return false;
      }

      // Сбрасываем флаг при изменении состояния соединения (reconnect)
      const newState = pusher.connection.state;
      if (currentConnectionState !== newState) {
        if (newState === 'disconnected' || newState === 'failed') {
          handlersSetup = false; // Сбрасываем при отключении
        }
        currentConnectionState = newState;
      }

      // Предотвращаем дублирование обработчиков
      if (handlersSetup && pusher.connection.state === 'connected') {
        return true;
      }

      // Удаляем старые обработчики, если они были установлены ранее
      try {
        pusher.connection.unbind('connected');
        pusher.connection.unbind('disconnected');
        pusher.connection.unbind('error');
        pusher.connection.unbind('state_change');
      } catch (e) {
        // Игнорируем ошибки при удалении несуществующих обработчиков
      }

      // Флаг для предотвращения множественных вызовов resubscribe
      let isResubscribing = false;
      
      const resubscribeOnce = () => {
        if (isResubscribing) {
          return;
        }
        isResubscribing = true;
        console.log('[WebSocket] Connected! Resubscribing to all channels...');
        import('./composables/useWebSocket').then(({ resubscribeAllChannels }) => {
          resubscribeAllChannels();
          // Сбрасываем флаг через небольшую задержку
          setTimeout(() => {
            isResubscribing = false;
          }, 1000);
        }).catch((err) => {
          console.error('[WebSocket] Failed to import resubscribeAllChannels:', err);
          isResubscribing = false;
        });
      };

      // Подписываемся на событие подключения
      pusher.connection.bind('connected', () => {
        resubscribeOnce();
      });
      
      // Логируем отключение и пытаемся переподключиться
      pusher.connection.bind('disconnected', () => {
        console.warn('[WebSocket] Disconnected! Attempting to reconnect...');
        isResubscribing = false; // Сбрасываем флаг при отключении
        
        // Pusher автоматически переподключается, но мы можем помочь
        // Проверяем состояние через небольшую задержку
        setTimeout(() => {
          if (pusher.connection?.state === 'disconnected' || pusher.connection?.state === 'failed') {
            console.warn('[WebSocket] Still disconnected, checking connection...');
            // Пытаемся принудительно переподключиться
            try {
              if (pusher.connection && typeof pusher.connection.connect === 'function') {
                pusher.connection.connect();
              }
            } catch (err) {
              console.error('[WebSocket] Failed to reconnect:', err);
            }
          }
        }, 1000);
      });

      // Обработка ошибок подключения
      pusher.connection.bind('error', (error) => {
        console.error('[WebSocket] Connection error:', error);
        console.error('[WebSocket] Error details:', {
          error: error,
          type: error?.type,
          data: error?.data,
          errorMessage: error?.error?.message || error?.message,
          wsHost,
          wsPort,
          appKey: appKey ? '***' : 'missing',
          useTLS,
          connectionState: pusher.connection?.state,
        });
        isResubscribing = false; // Сбрасываем флаг при ошибке
      });

      // Обработка изменений состояния
      pusher.connection.bind('state_change', (states) => {
        console.log('[WebSocket] State changed:', states);
        if (states.current === 'connected') {
          resubscribeOnce();
        } else if (states.current === 'disconnected' || states.current === 'failed') {
          isResubscribing = false; // Сбрасываем флаг при отключении
        } else if (states.current === 'unavailable') {
          console.error('[WebSocket] Connection unavailable!', {
            previous: states.previous,
            current: states.current,
            wsHost,
            wsPort,
            appKey: appKey ? '***' : 'missing',
            useTLS,
          });
          // Пытаемся переподключиться через небольшую задержку
          setTimeout(() => {
            if (pusher.connection?.state === 'unavailable' || pusher.connection?.state === 'disconnected') {
              console.warn('[WebSocket] Attempting to reconnect after unavailable state...');
              try {
                if (pusher.connection && typeof pusher.connection.connect === 'function') {
                  pusher.connection.connect();
                }
              } catch (err) {
                console.error('[WebSocket] Failed to reconnect:', err);
              }
            }
          }, 2000);
        }
      });

      handlersSetup = true;
      return true;
    };

    // Пытаемся настроить обработчики сразу
    if (!setupWebSocketHandlers()) {
      // Если connection еще не готов, ждем и пробуем снова
      let attempts = 0;
      const maxAttempts = 10;
      const checkInterval = setInterval(() => {
        attempts++;
        if (setupWebSocketHandlers() || attempts >= maxAttempts) {
          clearInterval(checkInterval);
          if (attempts >= maxAttempts) {
            console.warn('[WebSocket] Failed to setup handlers after', maxAttempts, 'attempts');
            console.warn('[WebSocket] Echo state:', {
              hasEcho: !!window.Echo,
              hasPusher: !!window.Echo?.connector?.pusher,
              hasConnection: !!window.Echo?.connector?.pusher?.connection,
              connectionState: window.Echo?.connector?.pusher?.connection?.state,
            });
          }
        }
      }, 200);
    }
    
    // Дополнительная диагностика через 3 секунды после инициализации
    // (увеличено время, так как подключение может занять больше времени)
    setTimeout(() => {
      if (window.Echo?.connector?.pusher) {
        const pusher = window.Echo.connector.pusher;
        const state = pusher.connection?.state;
        const socketId = pusher.connection?.socket_id;
        const channels = pusher.channels?.channels || {};
        const channelsCount = Object.keys(channels).length;
        
        console.log('[WebSocket] Connection status after 3s:', {
          state,
          socketId: socketId || 'none',
          hasChannels: channelsCount > 0,
          channelsCount,
        });
        
        if (state === 'connected') {
          console.log('[WebSocket] ✓ Connection established successfully');
        } else if (state === 'connecting') {
          console.info('[WebSocket] ⏳ Still connecting... This is normal, connection may take a few more seconds');
          // Проверяем еще раз через 2 секунды
          setTimeout(() => {
            const finalState = pusher.connection?.state;
            if (finalState === 'connected') {
              console.log('[WebSocket] ✓ Connection established after additional wait');
            } else {
              console.warn('[WebSocket] ⚠ Connection still not established. State:', finalState);
              console.warn('[WebSocket] Configuration:', {
                wsHost,
                wsPort,
                appKey: appKey ? '***' : 'missing',
                useTLS,
                wsEnabled,
              });
            }
          }, 2000);
        } else {
          console.warn('[WebSocket] ⚠ Connection not established. State:', state);
          console.warn('[WebSocket] Configuration:', {
            wsHost,
            wsPort,
            appKey: appKey ? '***' : 'missing',
            useTLS,
            wsEnabled,
          });
        }
      } else {
        console.error('[WebSocket] Echo or Pusher not initialized');
      }
    }, 3000);
  } else {
    console.warn('[bootstrap.js] Echo не инициализирован:', { wsEnabled, appKey: !!appKey });
  }
} catch (e) {
  console.error('[bootstrap.js] Ошибка инициализации Echo:', e?.message || e);
  window.Echo = undefined;
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
  if (!window.Echo) return
  window.Echo.channel('hydro.alerts').listen('.App\\Events\\AlertCreated', (e) => {
    handler?.(e)
  })
}

// Global error logging
window.addEventListener('error', (event) => {
  // eslint-disable-next-line no-console
  console.error('[WINDOW ERROR]', event?.message, event?.error);
});
window.addEventListener('unhandledrejection', (event) => {
  // Игнорируем отмененные запросы Inertia.js
  const reason = event?.reason;
  if (reason?.code === 'ERR_CANCELED' || reason?.name === 'CanceledError' || reason?.message === 'canceled') {
    // Не логируем отмененные запросы
    event.preventDefault();
    return;
  }
  // eslint-disable-next-line no-console
  console.error('[UNHANDLED REJECTION]', reason || event);
});

// Принудительное включение всех логов
console.log('[bootstrap.js] Инициализация завершена, все логи включены')
console.log('[bootstrap.js] window.console доступен:', typeof window.console)
console.log('[bootstrap.js] console.log доступен:', typeof console.log)
console.log('[bootstrap.js] console.error доступен:', typeof console.error)
console.log('[bootstrap.js] console.warn доступен:', typeof console.warn)
