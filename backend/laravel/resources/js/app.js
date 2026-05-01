import '../css/app.css';
import './bootstrap';

import { createInertiaApp } from '@inertiajs/vue3';
import { resolvePageComponent } from 'laravel-vite-plugin/inertia-helpers';
import { createApp, h } from 'vue';
import { createPinia } from 'pinia';
import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query';
import { RecycleScroller, DynamicScroller, DynamicScrollerItem } from 'vue-virtual-scroller';
import { setupRouterGuards } from './utils/routerGuards';
import { installZiggy } from './utils/ziggy';
import { setupVueErrorHandlers } from './utils/vueErrorHandlers';
import { setToastHandler } from './utils/apiClient';
import { useToast } from './composables/useToast';
import { clickOutside } from './directives/clickOutside';

// Подключаем единый global-показ Toast для axios-interceptor'а.
// Ранее это делал `useApi(showToast)` как side-effect первой инициализации;
// после миграции на typed `services/api/` мы регистрируем обработчик один раз
// на уровне приложения. Без этого axios ошибки не попадали в UI.
const { showToast: __bootstrapShowToast } = useToast();
setToastHandler(__bootstrapShowToast);

const appName = import.meta.env.VITE_APP_NAME || 'Автоматика теплицы';

createInertiaApp({
    title: (title) => {
        const t = typeof title === 'string' ? title.trim() : '';
        return t ? `${t} — ${appName}` : appName;
    },
    resolve: (name) =>
        resolvePageComponent(
            `./Pages/${name}.vue`,
            import.meta.glob('./Pages/**/*.vue'),
        ),
    setup({ el, App, props, plugin }) {
        const vueApp = createApp({ render: () => h(App, props) });
        const pinia = createPinia();
        
        // Настраиваем обработчики ошибок Vue
        setupVueErrorHandlers(vueApp);
        
        // Регистрируем компоненты виртуализации глобально
        vueApp.component('RecycleScroller', RecycleScroller);
        vueApp.component('DynamicScroller', DynamicScroller);
        vueApp.component('DynamicScrollerItem', DynamicScrollerItem);

        vueApp.directive('click-outside', clickOutside);
        
        vueApp.use(plugin);
        vueApp.use(pinia);

        const queryClient = new QueryClient({
            defaultOptions: {
                queries: {
                    staleTime: 30_000,
                    retry: 1,
                    refetchOnWindowFocus: false,
                },
                mutations: {
                    retry: 0,
                },
            },
        });
        vueApp.use(VueQueryPlugin, { queryClient });

        // Безопасная установка ZiggyVue
        installZiggy(vueApp);
        
        // Настраиваем защиту от циклических перезагрузок
        setupRouterGuards();
        
        return vueApp.mount(el);
    },
    progress: {
        color: 'var(--text-dim)',
        delay: 100, // Задержка перед показом индикатора (100ms)
    },
    // Отключаем логирование переходов Inertia.js
    // Сообщения "Перешёл на ..." больше не будут отображаться
});

// HMR cleanup: восстанавливаем оригинальные методы router при перезагрузке модуля
if (typeof import.meta !== 'undefined' && import.meta.hot) {
  import.meta.hot.dispose(() => {
    import('./utils/routerGuards').then(({ restoreRouterMethods }) => {
      restoreRouterMethods();
    }).catch(() => {
      // Игнорируем ошибки при импорте (модуль может быть недоступен)
    });
  });
}
