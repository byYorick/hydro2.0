import '../css/app.css';
import './bootstrap';

import { createInertiaApp } from '@inertiajs/vue3';
import { resolvePageComponent } from 'laravel-vite-plugin/inertia-helpers';
import { createApp, h } from 'vue';
import { createPinia } from 'pinia';
import { RecycleScroller, DynamicScroller, DynamicScrollerItem } from 'vue-virtual-scroller';
import { setupRouterGuards } from './utils/routerGuards';
import { installZiggy } from './utils/ziggy';
import { setupVueErrorHandlers } from './utils/vueErrorHandlers';

const appName = import.meta.env.VITE_APP_NAME || 'Laravel';

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
        
        // Настраиваем обработчики ошибок Vue
        setupVueErrorHandlers(vueApp);
        
        // Регистрируем компоненты виртуализации глобально
        vueApp.component('RecycleScroller', RecycleScroller);
        vueApp.component('DynamicScroller', DynamicScroller);
        vueApp.component('DynamicScrollerItem', DynamicScrollerItem);
        
        vueApp.use(plugin);
        vueApp.use(pinia);
        
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
