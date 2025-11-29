import '../css/app.css';
import './bootstrap';

import { createInertiaApp } from '@inertiajs/vue3';
import { resolvePageComponent } from 'laravel-vite-plugin/inertia-helpers';
import { createApp, h } from 'vue';
import { createPinia } from 'pinia';
// Безопасный импорт ZiggyVue для предотвращения ошибок
// Используем условный импорт для обработки случая, когда Ziggy не установлен
import { RecycleScroller, DynamicScroller, DynamicScrollerItem } from 'vue-virtual-scroller';
import { logger } from './utils/logger';

const appName = import.meta.env.VITE_APP_NAME || 'Laravel';

let reloadCount = 0;
let lastReloadTime = 0;
let lastReloadUrl = '';
const MAX_RELOADS_PER_SECOND = 3;
const RELOAD_WINDOW_MS = 1000;

function shouldPreventReload(url) {
  const now = Date.now();
  const currentUrl = url || window.location.pathname;
  
  if (currentUrl !== lastReloadUrl) {
    reloadCount = 0;
    lastReloadTime = now;
    lastReloadUrl = currentUrl;
    return false;
  }
  
  if (now - lastReloadTime > RELOAD_WINDOW_MS) {
    reloadCount = 0;
    lastReloadTime = now;
    lastReloadUrl = currentUrl;
    return false;
  }
  
  reloadCount++;
  if (reloadCount > MAX_RELOADS_PER_SECOND) {
    logger.warn('[app.js] Too many reloads to same URL detected, preventing reload', {
      count: reloadCount,
      window: RELOAD_WINDOW_MS,
      url: currentUrl,
    });
    return true;
  }
  lastReloadTime = now;
  return false;
}

createInertiaApp({
    title: (title) => `${title} - ${appName}`,
    resolve: (name) =>
        resolvePageComponent(
            `./Pages/${name}.vue`,
            import.meta.glob('./Pages/**/*.vue'),
        ),
    setup({ el, App, props, plugin }) {
        const vueApp = createApp({ render: () => h(App, props) });
        const pinia = createPinia();
        // Обработка ошибок Vue без перезагрузки страницы
        vueApp.config.errorHandler = (err, instance, info) => {
            // Игнорируем отмененные запросы Inertia.js
            if (err?.code === 'ERR_CANCELED' || err?.name === 'CanceledError' || err?.message === 'canceled') {
                return;
            }
            // Логируем ошибку, но НЕ перезагружаем страницу
            // eslint-disable-next-line no-console
            logger.error('[VUE ERROR]', { err, info, instance });
            // НЕ вызываем location.reload() или router.reload() здесь
            // Ошибки должны обрабатываться через ErrorBoundary компонент
        };
        vueApp.config.warnHandler = (msg, instance, trace) => {
            import('./utils/logger').then(({ logger }) => {
                logger.warn('[VUE WARN]', msg, { trace, instance });
            });
        };
        // Регистрируем компоненты виртуализации глобально
        vueApp.component('RecycleScroller', RecycleScroller);
        vueApp.component('DynamicScroller', DynamicScroller);
        vueApp.component('DynamicScrollerItem', DynamicScrollerItem);
        
        vueApp.use(plugin);
        vueApp.use(pinia);
        
        // Устанавливаем версию Vue СИНХРОННО перед любым использованием ZiggyVue
        // ZiggyVue проверяет версию Vue через parseInt(vueApp.version)
        // Если версия не установлена или undefined, parseInt вернет NaN, и ZiggyVue попытается использовать Vue 2 API (t.mixin)
        // Vue 3 не имеет метода mixin, что приводит к ошибке "can't access property 'extend' of undefined"
        // Устанавливаем версию явно в формате "3.x.x" для правильного определения версии
        if (!vueApp.version || typeof vueApp.version !== 'string') {
            // Устанавливаем версию Vue явно в формате строки "3.x.x"
            // parseInt("3.4.0") вернет 3, что больше 2, и ZiggyVue будет использовать Vue 3 API
            Object.defineProperty(vueApp, 'version', {
                value: '3.4.0',
                writable: false,
                configurable: false,
                enumerable: true,
            });
        }
        
        // Безопасный импорт ZiggyVue внутри setup
        // Используем динамический импорт для безопасной загрузки
        // Убеждаемся, что Vue полностью инициализирован перед использованием ZiggyVue
        (async () => {
            try {
                const ziggyModule = await import('../../vendor/tightenco/ziggy/dist/index.esm.js');
                const ZiggyVue = ziggyModule.ZiggyVue || ziggyModule.default?.ZiggyVue || ziggyModule.default;
                
                // Проверяем версию Vue перед использованием ZiggyVue
                const vueVersion = parseInt(vueApp.version || '0');
                if (vueVersion <= 2) {
                    logger.error('[app.js] Vue version is too old for ZiggyVue', {
                        version: vueApp.version,
                        parsed: vueVersion,
                        note: 'ZiggyVue requires Vue 3. Setting version to 3.4.0',
                    });
                    Object.defineProperty(vueApp, 'version', {
                        value: '3.4.0',
                        writable: false,
                        configurable: false,
                        enumerable: true,
                    });
                }
                
                if (ZiggyVue && typeof ZiggyVue.install === 'function') {
                    // Передаем vueApp и конфигурацию Ziggy в install()
                    // ZiggyVue.install принимает два параметра: app и config
                    // Если config не передан, ZiggyVue попытается найти Ziggy глобально
                    ZiggyVue.install(vueApp, typeof Ziggy !== 'undefined' ? Ziggy : undefined);
                } else if (ZiggyVue && typeof ZiggyVue === 'function') {
                    // Если ZiggyVue - это функция, используем её как плагин
                    vueApp.use(ZiggyVue);
                } else {
                    logger.warn('[app.js] ZiggyVue is not a valid Vue plugin', { ZiggyVue });
                }
            } catch (err) {
                // Если Ziggy не установлен или не доступен, продолжаем без него
                logger.warn('[app.js] ZiggyVue not available, continuing without it', { err });
            }
        })();
        
        // Удален обработчик router.on('success') - он вызывал множественные переинициализации
        // WebSocket соединение должно управляться только через bootstrap.js и echoClient.ts
        // Inertia.js обновления страницы не должны вызывать переинициализацию WebSocket
        
        // Добавляем защиту от циклических перезагрузок через Inertia.js
        import('@inertiajs/vue3').then(({ router }) => {
            // Перехватываем все вызовы router.reload() и router.visit() для предотвращения циклов
            const originalReload = router.reload.bind(router);
            const originalVisit = router.visit.bind(router);
            
            router.reload = function(options) {
                // Проверяем только reload() на текущий URL
                if (shouldPreventReload(window.location.pathname)) {
                    logger.warn('[app.js] Prevented router.reload() due to reload limit', {
                        options,
                        currentUrl: window.location.pathname,
                    });
                    return Promise.resolve();
                }
                logger.debug('[app.js] router.reload() called', { options });
                return originalReload(options);
            };
            
            router.visit = function(url, options) {
                // Блокируем только visit() на тот же URL, легитимная навигация разрешена
                // Если URL отличается, это нормальная навигация, не блокируем
                const targetUrl = typeof url === 'string' ? url : url?.url || window.location.pathname
                if (shouldPreventReload(targetUrl) && targetUrl === window.location.pathname) {
                    logger.warn('[app.js] Prevented router.visit() to same URL due to reload limit', {
                        url: targetUrl,
                        currentUrl: window.location.pathname,
                        options,
                    });
                    return Promise.resolve();
                }
                // Легитимная навигация на другой URL разрешена, не логируем каждый вызов
                // Убрано логирование переходов по запросу пользователя
                return originalVisit(url, options);
            };
        });
        
        return vueApp.mount(el);
    },
    progress: {
        color: '#4B5563',
        delay: 100, // Задержка перед показом индикатора (100ms)
    },
    // Отключаем логирование переходов Inertia.js
    // Сообщения "Перешёл на ..." больше не будут отображаться
});
