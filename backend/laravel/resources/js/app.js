import '../css/app.css';
import './bootstrap';

import { createInertiaApp } from '@inertiajs/vue3';
import { resolvePageComponent } from 'laravel-vite-plugin/inertia-helpers';
import { createApp, h } from 'vue';
import { createPinia } from 'pinia';
// ИСПРАВЛЕНО: Безопасный импорт ZiggyVue для предотвращения ошибок
// Используем условный импорт для обработки случая, когда Ziggy не установлен
import { RecycleScroller, DynamicScroller, DynamicScrollerItem } from 'vue-virtual-scroller';
import { logger } from './utils/logger';

const appName = import.meta.env.VITE_APP_NAME || 'Laravel';

// ИСПРАВЛЕНО: Защита от циклических перезагрузок
let reloadCount = 0;
let lastReloadTime = 0;
const MAX_RELOADS_PER_SECOND = 3;
const RELOAD_WINDOW_MS = 1000;

function shouldPreventReload() {
  const now = Date.now();
  if (now - lastReloadTime > RELOAD_WINDOW_MS) {
    reloadCount = 0;
    lastReloadTime = now;
    return false;
  }
  reloadCount++;
  if (reloadCount > MAX_RELOADS_PER_SECOND) {
    logger.warn('[app.js] Too many reloads detected, preventing reload', {
      count: reloadCount,
      window: RELOAD_WINDOW_MS,
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
        // ИСПРАВЛЕНО: Обработка ошибок Vue без перезагрузки страницы
        vueApp.config.errorHandler = (err, instance, info) => {
            // Игнорируем отмененные запросы Inertia.js
            if (err?.code === 'ERR_CANCELED' || err?.name === 'CanceledError' || err?.message === 'canceled') {
                return;
            }
            // ИСПРАВЛЕНО: Логируем ошибку, но НЕ перезагружаем страницу
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
        
        // ИСПРАВЛЕНО: Устанавливаем версию Vue СИНХРОННО перед любым использованием ZiggyVue
        // ZiggyVue проверяет версию Vue через parseInt(vueApp.version)
        // Если версия не установлена или undefined, parseInt вернет NaN, и ZiggyVue попытается использовать Vue 2 API (t.mixin)
        // Vue 3 не имеет метода mixin, что приводит к ошибке "can't access property 'extend' of undefined"
        // Устанавливаем версию явно в формате "3.x.x" для правильного определения версии
        if (!vueApp.version || typeof vueApp.version !== 'string') {
            // ИСПРАВЛЕНО: Устанавливаем версию Vue явно в формате строки "3.x.x"
            // parseInt("3.4.0") вернет 3, что больше 2, и ZiggyVue будет использовать Vue 3 API
            Object.defineProperty(vueApp, 'version', {
                value: '3.4.0',
                writable: false,
                configurable: false,
                enumerable: true,
            });
        }
        
        // ИСПРАВЛЕНО: Безопасный импорт ZiggyVue внутри setup
        // Используем динамический импорт для безопасной загрузки
        // ИСПРАВЛЕНО: Убеждаемся, что Vue полностью инициализирован перед использованием ZiggyVue
        (async () => {
            try {
                const ziggyModule = await import('../../vendor/tightenco/ziggy/dist/index.esm.js');
                const ZiggyVue = ziggyModule.ZiggyVue || ziggyModule.default?.ZiggyVue || ziggyModule.default;
                
                // ИСПРАВЛЕНО: Проверяем версию Vue перед использованием ZiggyVue
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
                    // ИСПРАВЛЕНО: Передаем vueApp и конфигурацию Ziggy в install()
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
        
        // ИСПРАВЛЕНО: Удален обработчик router.on('success') - он вызывал множественные переинициализации
        // WebSocket соединение должно управляться только через bootstrap.js и echoClient.ts
        // Inertia.js обновления страницы не должны вызывать переинициализацию WebSocket
        
        // ИСПРАВЛЕНО: Добавляем защиту от циклических перезагрузок через Inertia.js
        import('@inertiajs/vue3').then(({ router }) => {
            // Перехватываем все вызовы router.reload() и router.visit() для предотвращения циклов
            const originalReload = router.reload.bind(router);
            const originalVisit = router.visit.bind(router);
            
            router.reload = function(options) {
                if (shouldPreventReload()) {
                    logger.warn('[app.js] Prevented router.reload() due to reload limit', {
                        options,
                    });
                    return Promise.resolve();
                }
                logger.debug('[app.js] router.reload() called', { options });
                return originalReload(options);
            };
            
            router.visit = function(url, options) {
                // Разрешаем visit, но логируем для отладки
                if (shouldPreventReload() && url === window.location.pathname) {
                    logger.warn('[app.js] Prevented router.visit() to same URL due to reload limit', {
                        url,
                        options,
                    });
                    return Promise.resolve();
                }
                logger.debug('[app.js] router.visit() called', { url, options });
                return originalVisit(url, options);
            };
        });
        
        return vueApp.mount(el);
    },
    progress: {
        color: '#4B5563',
        delay: 100, // Задержка перед показом индикатора (100ms)
    },
});
