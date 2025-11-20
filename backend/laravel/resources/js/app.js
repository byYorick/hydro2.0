import '../css/app.css';
import './bootstrap';

import { createInertiaApp } from '@inertiajs/vue3';
import { resolvePageComponent } from 'laravel-vite-plugin/inertia-helpers';
import { createApp, h } from 'vue';
import { createPinia } from 'pinia';
import { ZiggyVue } from '../../vendor/tightenco/ziggy';
import { RecycleScroller, DynamicScroller, DynamicScrollerItem } from 'vue-virtual-scroller';

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
        // Verbose Vue error/warn -> console
        vueApp.config.errorHandler = (err, instance, info) => {
            // Игнорируем отмененные запросы Inertia.js
            if (err?.code === 'ERR_CANCELED' || err?.name === 'CanceledError' || err?.message === 'canceled') {
                return;
            }
            // eslint-disable-next-line no-console
            console.error('[VUE ERROR]', err, { info, instance });
        };
        vueApp.config.warnHandler = (msg, instance, trace) => {
            // eslint-disable-next-line no-console
            console.warn('[VUE WARN]', msg, { trace, instance });
        };
        // Регистрируем компоненты виртуализации глобально
        vueApp.component('RecycleScroller', RecycleScroller);
        vueApp.component('DynamicScroller', DynamicScroller);
        vueApp.component('DynamicScrollerItem', DynamicScrollerItem);
        
        return vueApp
            .use(plugin)
            .use(pinia)
            .use(ZiggyVue)
            .mount(el);
    },
    progress: {
        color: '#4B5563',
        delay: 100, // Задержка перед показом индикатора (100ms)
    },
});
