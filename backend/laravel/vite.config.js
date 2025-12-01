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
        // ИСПРАВЛЕНО: Используем 0.0.0.0 для прослушивания (чтобы принимать соединения из сети)
        // Но для HMR и клиентских подключений используем localhost (см. hmr.host)
        // nginx прокси будет работать с 127.0.0.1 внутри контейнера
        host: process.env.VITE_HOST || '0.0.0.0',
        port: 5173,
        strictPort: true,
        cors: {
            origin: (origin, callback) => {
                callback(null, true);
            },
            credentials: false,
            methods: ['GET', 'HEAD', 'PUT', 'PATCH', 'POST', 'DELETE', 'OPTIONS'],
            allowedHeaders: ['*'],
        },
        hmr: {
            host: 'localhost',
            port: 5173,
            clientPort: 5173,
            path: '/@vite/client',
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
    // Оптимизация сборки для production
    build: {
        // Production optimizations (esbuild быстрее чем terser)
        minify: 'esbuild',
        cssCodeSplit: true, // Разбивать CSS на чанки для production
        sourcemap: false, // Отключить sourcemaps в production для скорости
        // Удалить console и debugger в production
        esbuild: {
            drop: process.env.NODE_ENV === 'production' ? ['console', 'debugger'] : [],
        },
        rollupOptions: {
            output: {
                // Оптимизация для production
                manualChunks: (id) => {
                    // Разделение vendor chunks для лучшего кеширования
                    // Vue должен быть в основном bundle, а не в отдельном chunk
                    // для правильной синхронной загрузки
                    if (id.includes('node_modules')) {
                        // Vue и его зависимости не разделяем, они будут в основном bundle
                        if (id.includes('vue') || id.includes('@vue')) {
                            return null; // Возвращаем null, чтобы Vue был в основном bundle
                        }
                        if (id.includes('echarts')) {
                            return 'echarts-vendor';
                        }
                        return 'vendor';
                    }
                },
                // Оптимизация имен файлов
                chunkFileNames: 'js/[name]-[hash].js',
                entryFileNames: 'js/[name]-[hash].js',
                assetFileNames: (assetInfo) => {
                    if (assetInfo.name && assetInfo.name.endsWith('.css')) {
                        return 'css/[name]-[hash][extname]';
                    }
                    return 'assets/[name]-[hash][extname]';
                },
            },
        },
        // Увеличить лимит предупреждений для production
        chunkSizeWarningLimit: 1000,
        // Оптимизация для production (используется esbuild по умолчанию, terser опционален)
        // Если нужен terser, установите: npm install -D terser
        // terserOptions: {
        //     compress: {
        //         drop_console: true, // Удалить console.log в production
        //         drop_debugger: true,
        //     },
        // },
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
            detectTls: false, // Отключить автоматическое определение TLS
            // Явно указываем devServerUrl для правильной генерации URL
            // Используем localhost:8080 (через nginx прокси), а не 0.0.0.0
            // Браузер не может использовать 0.0.0.0 для запросов
            devServerUrl: process.env.VITE_DEV_SERVER_URL || 'http://localhost:8080',
            // Использовать прокси через nginx вместо прямых ссылок на Vite
            buildDirectory: 'build',
            hotFile: 'public/hot',
        }),
        vue({
            template: {
                transformAssetUrls: {
                    base: null,
                    includeAbsolute: false,
                },
                compilerOptions: {
                    // Production optimizations для Vue
                    isCustomElement: (tag) => false,
                },
            },
            // Vue production mode
            isProduction: process.env.NODE_ENV === 'production',
        }),
    ],
    // Оптимизация зависимостей для снижения нагрузки
    optimizeDeps: {
        include: ['vue', '@inertiajs/vue3', 'vue-virtual-scroller'],
        exclude: [],
        force: false, // Не пересобирать принудительно
        esbuildOptions: {
            resolveExtensions: ['.mjs', '.js', '.mts', '.ts', '.jsx', '.tsx', '.json'],
            // ИСПРАВЛЕНО: Отключаем source maps для оптимизированных зависимостей
            // Это устраняет ошибки "No sources are declared in this source map"
            sourcemap: false,
        },
    },
    // Кеш для оптимизированных зависимостей
    cacheDir: 'node_modules/.vite',
});
