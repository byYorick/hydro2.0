module.exports = {
  root: true,
  env: {
    browser: true,
    es2021: true,
    node: true,
  },
  extends: [
    'eslint:recommended',
    'plugin:vue/vue3-essential',
    'plugin:vue/vue3-strongly-recommended',
    'plugin:vue/vue3-recommended',
    'plugin:@typescript-eslint/recommended',
    '@vue/eslint-config-typescript',
  ],
  parser: 'vue-eslint-parser',
  parserOptions: {
    ecmaVersion: 2021,
    parser: '@typescript-eslint/parser',
    sourceType: 'module',
  },
  plugins: [
    'vue',
    '@typescript-eslint',
  ],
  rules: {
    // Vue specific rules
    'vue/multi-word-component-names': 'off',
    'vue/no-v-html': 'warn',
    'vue/no-side-effects-in-computed-properties': 'warn',
    'vue/no-mutating-props': 'error',
    'vue/require-default-prop': 'off',
    'vue/require-explicit-emits': 'warn',
    'no-case-declarations': 'warn',
    'vue/html-self-closing': ['warn', {
      html: {
        void: 'always',
        normal: 'never',
        component: 'always',
      },
    }],
    
    // TypeScript specific rules
    '@typescript-eslint/no-explicit-any': 'warn',
    '@typescript-eslint/no-unused-vars': ['warn', {
      argsIgnorePattern: '^_',
      varsIgnorePattern: '^_',
    }],
    '@typescript-eslint/explicit-module-boundary-types': 'off',
    '@typescript-eslint/no-non-null-assertion': 'warn',
    '@typescript-eslint/ban-ts-comment': 'off',
    
    // General rules
    'no-console': ['warn', { allow: ['warn', 'error'] }],
    'no-debugger': process.env.NODE_ENV === 'production' ? 'error' : 'warn',
    'no-unused-vars': 'off', // Используем TypeScript версию
    'prefer-const': 'warn',
    'no-var': 'error',

    // Фаза 3: граница API-слоя.
    //
    // `@/utils/apiClient` — строгий error. На момент Фазы 3 единственное место,
    //   которое его импортирует — `services/api/_client.ts` и legacy `composables/useApi.ts`
    //   (whitelist в overrides ниже).
    //
    // `@/composables/useApi` — warn (не error), потому что 50+ composables ещё
    //   используют его. Правило служит маркером долга: каждый новый файл с
    //   useApi виден в lint, но не ломает CI. Миграция идёт доменно.
    //
    // Новый код обязан использовать: `import { api } from '@/services/api'`.
    'no-restricted-imports': ['error', {
      paths: [
        {
          name: '@/utils/apiClient',
          message: 'Импорт apiClient напрямую запрещён. Используй `import { api } from \'@/services/api\'` или добавь типизированный метод в services/api/<domain>.ts.',
        },
      ],
    }],
    '@typescript-eslint/no-restricted-imports': 'off',
  },
  overrides: [
    {
      // Файлы, которым разрешено импортировать apiClient напрямую:
      //   - `services/api/_client.ts` — внутренний client services/api/
      //   - `composables/useRateLimitedApi.ts` — нужен raw axios для Retry-After
      //   - `app.js` — регистрирует global toast handler при bootstrap
      // Всё остальное должно ходить через `import { api } from '@/services/api'`.
      files: [
        'resources/js/services/api/_client.ts',
        'resources/js/composables/useRateLimitedApi.ts',
        'resources/js/app.js',
      ],
      rules: {
        'no-restricted-imports': 'off',
      },
    },
    {
      // Warn-маркер: если кто-то в новом коде попытается импортировать
      // `@/utils/apiClient` или несуществующий `@/composables/useApi`.
      files: ['resources/js/**/*.{ts,tsx,vue}'],
      excludedFiles: [
        'resources/js/services/api/**',
      ],
      rules: {
        'no-restricted-imports': ['warn', {
          paths: [
            {
              name: '@/utils/apiClient',
              message: 'Импорт apiClient напрямую запрещён. Используй `import { api } from \'@/services/api\'`.',
            },
            {
              name: '@/composables/useApi',
              message: 'useApi удалён в Phase 4. Используй `import { api } from \'@/services/api\'`.',
            },
          ],
        }],
      },
    },
    {
      files: [
        'resources/js/**/__tests__/**/*.{js,ts,tsx,vue}',
        'resources/js/**/*.{spec,test}.{js,ts,tsx}',
        'tests/**/*.ts',
      ],
      rules: {
        '@typescript-eslint/no-explicit-any': 'off',
        '@typescript-eslint/no-non-null-assertion': 'off',
        '@typescript-eslint/no-unused-vars': 'off',
        'no-console': 'off',
        'vue/one-component-per-file': 'off',
        'vue/require-explicit-emits': 'off',
        'no-restricted-imports': 'off',
      },
    },
    {
      files: [
        'resources/js/**/*.{ts,tsx,vue}',
        'vitest.setup.ts',
      ],
      rules: {
        '@typescript-eslint/no-explicit-any': 'off',
      },
    },
  ],
  ignorePatterns: [
    'dist',
    'node_modules',
    'public/build',
    'vendor',
    '*.min.js',
    'coverage',
  ],
};
