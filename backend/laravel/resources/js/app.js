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

// Храним оригинальные методы router для предотвращения наложения обёрток при HMR
let originalRouterMethods = {
  reload: null,
  visit: null,
  isWrapped: false
};

// Маркер для определения обёрнутых методов
const WRAPPER_MARKER = Symbol('routerWrapper');

function shouldPreventReload(url) {
  const now = Date.now();
  // Используем полный URL включая query параметры для корректного сравнения
  // Это позволяет различать переходы на тот же путь с разными query (например, ?page=1 vs ?page=2)
  const currentUrl = url || window.location.pathname + window.location.search;
  
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
            // Проверяем, не обёрнуты ли уже методы (защита от HMR наложения обёрток)
            // Проверяем по наличию маркера на методах
            const isReloadWrapped = router.reload && router.reload[WRAPPER_MARKER] === true;
            const isVisitWrapped = router.visit && router.visit[WRAPPER_MARKER] === true;
            
            if (isReloadWrapped || isVisitWrapped) {
                // Методы уже обёрнуты, восстанавливаем оригинальные перед повторной обёрткой
                logger.debug('[app.js] Router methods already wrapped, restoring originals before re-wrap', {
                    isReloadWrapped,
                    isVisitWrapped,
                });
                
                if (originalRouterMethods.reload) {
                    router.reload = originalRouterMethods.reload;
                }
                if (originalRouterMethods.visit) {
                    router.visit = originalRouterMethods.visit;
                }
            }
            
            // Сохраняем оригинальные методы (если ещё не сохранены или были восстановлены)
            if (!originalRouterMethods.reload || originalRouterMethods.reload[WRAPPER_MARKER] === true) {
                originalRouterMethods.reload = router.reload.bind(router);
            }
            if (!originalRouterMethods.visit || originalRouterMethods.visit[WRAPPER_MARKER] === true) {
                originalRouterMethods.visit = router.visit.bind(router);
            }
            
            // Перехватываем все вызовы router.reload() и router.visit() для предотвращения циклов
            const wrappedReload = function(options) {
                // Проверяем только reload() на текущий URL (включая query параметры)
                const currentUrl = window.location.pathname + window.location.search;
                if (shouldPreventReload(currentUrl)) {
                    logger.warn('[app.js] Prevented router.reload() due to reload limit', {
                        options,
                        currentUrl: currentUrl,
                    });
                    return Promise.resolve();
                }
                logger.debug('[app.js] router.reload() called', { 
                    options,
                    currentUrl: currentUrl,
                    stack: new Error().stack,
                });
                return originalRouterMethods.reload(options);
            };
            
            // Помечаем обёрнутый метод маркером
            wrappedReload[WRAPPER_MARKER] = true;
            router.reload = wrappedReload;
            
            const wrappedVisit = function(url, options) {
                // Блокируем только visit() на тот же URL (включая query параметры), легитимная навигация разрешена
                // Если URL отличается, это нормальная навигация, не блокируем
                const targetUrl = typeof url === 'string' ? url : url?.url || window.location.pathname
                const currentUrl = window.location.pathname + window.location.search;
                
                // Логируем все вызовы router.visit() для отладки автоматических переходов
                logger.debug('[app.js] router.visit() called', {
                    url: targetUrl,
                    currentUrl: currentUrl,
                    options,
                    stack: new Error().stack,
                });
                
                // Сравниваем полные URL включая query параметры
                if (shouldPreventReload(targetUrl) && targetUrl === currentUrl) {
                    logger.warn('[app.js] Prevented router.visit() to same URL due to reload limit', {
                        url: targetUrl,
                        currentUrl: currentUrl,
                        options,
                    });
                    return Promise.resolve();
                }
                return originalRouterMethods.visit(url, options);
            };
            
            // Помечаем обёрнутый метод маркером
            wrappedVisit[WRAPPER_MARKER] = true;
            router.visit = wrappedVisit;
            
            // Помечаем, что методы обёрнуты
            originalRouterMethods.isWrapped = true;
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

// HMR cleanup: восстанавливаем оригинальные методы router при перезагрузке модуля
if (typeof import.meta !== 'undefined' && import.meta.hot) {
  import.meta.hot.dispose(() => {
    // Восстанавливаем оригинальные методы router, если они были обёрнуты
    import('@inertiajs/vue3').then(({ router }) => {
      if (originalRouterMethods.reload && router.reload && router.reload[WRAPPER_MARKER] === true) {
        router.reload = originalRouterMethods.reload;
        logger.debug('[app.js] HMR: Restored original router.reload');
      }
      if (originalRouterMethods.visit && router.visit && router.visit[WRAPPER_MARKER] === true) {
        router.visit = originalRouterMethods.visit;
        logger.debug('[app.js] HMR: Restored original router.visit');
      }
    }).catch(() => {
      // Игнорируем ошибки при импорте (модуль может быть недоступен)
    });
    
    // Сбрасываем флаг обёртки, чтобы при следующей инициализации методы были восстановлены
    originalRouterMethods.isWrapped = false;
    // Очищаем счётчики reload для предотвращения ложных блокировок
    reloadCount = 0;
    lastReloadTime = 0;
    lastReloadUrl = '';
  });
}
