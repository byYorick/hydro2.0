import { defineConfig } from 'vite';
import laravel from 'laravel-vite-plugin';
import vue from '@vitejs/plugin-vue';
import { resolve } from 'path';

export default defineConfig({
    resolve: {
        alias: {
            '@': resolve(__dirname, './resources/js'),
        },
    },
    server: {
        host: '0.0.0.0',
        port: 5173,
        strictPort: true,
        origin: 'http://localhost:5173',
        cors: {
            origin: ['http://localhost:8080'],
            credentials: true,
        },
        hmr: {
            host: 'localhost',
            port: 5173,
            protocol: 'ws',
        },
        watch: {
            usePolling: true, // Для Docker на Windows
            interval: 2000, // Увеличен интервал до 2 секунд для снижения нагрузки на CPU
            ignored: [
                '**/node_modules/**',
                '**/.git/**',
                '**/storage/**',
                '**/vendor/**',
                '**/bootstrap/cache/**',
                '**/public/build/**',
                '**/public/hot',
                '**/.env*',
                '**/tests/**',
                '**/database/**',
            ],
        },
        // Оптимизация для быстрой загрузки
        fs: {
            strict: false,
        },
    },
    // Оптимизация сборки
    build: {
        cssCodeSplit: false, // Не разбивать CSS на чанки для dev
        rollupOptions: {
            output: {
                manualChunks: undefined, // Отключить разбиение на чанки в dev
            },
        },
    },
    plugins: [
        laravel({
            input: 'resources/js/app.js',
            refresh: [
                'resources/views/**',
                'resources/js/**',
                'app/Http/Controllers/**',
                'routes/**',
            ], // Ограничиваем refresh только нужными файлами для снижения нагрузки
        }),
        vue({
            template: {
                transformAssetUrls: {
                    base: null,
                    includeAbsolute: false,
                },
            },
        }),
    ],
    // Оптимизация зависимостей для снижения нагрузки
    optimizeDeps: {
        include: ['vue', '@inertiajs/vue3'],
        exclude: [],
        force: false, // Не пересобирать принудительно
    },
    // Кеш для оптимизированных зависимостей
    cacheDir: 'node_modules/.vite',
});
