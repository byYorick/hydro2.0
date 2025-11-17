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

const wsHost = import.meta.env.VITE_WS_HOST || window.location.hostname;
const wsPort = Number(import.meta.env.VITE_WS_PORT || 8080);
const useTLS = String(import.meta.env.VITE_WS_TLS || 'false') === 'true';
const cluster = import.meta.env.VITE_PUSHER_APP_CLUSTER || 'mt1';
const appKey = import.meta.env.VITE_PUSHER_APP_KEY;
const wsEnabled = String(import.meta.env.VITE_ENABLE_WS || 'false') === 'true';

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
    window.Echo = new Echo({
      broadcaster: 'pusher',
      key: appKey,
      cluster,
      wsHost,
      wsPort,
      forceTLS: useTLS,
      disableStats: true,
      enabledTransports: ['ws', 'wss'],
    });
  }
} catch (e) {
  console.warn('Echo init disabled:', e?.message || e);
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
