<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { Head, Link } from '@inertiajs/vue3'
import ToastContainer from '@/Components/ToastContainer.vue'
import { route } from '@/utils/route'
import { useInertiaForm } from '@/composables/useInertiaForm'

interface Props {
  canResetPassword?: boolean
  status?: string
}

const props = defineProps<Props>()

interface LoginFormData {
  email: string
  password: string
  remember: boolean
  [key: string]: any
}

type ThemeMode = 'light' | 'dark'
type LoginField = 'email' | 'password'

const themeStorageKey = 'hydro.ui.theme'

function getPreferredTheme(): ThemeMode {
  if (typeof window === 'undefined') {
    return 'light'
  }

  const stored = window.localStorage.getItem(themeStorageKey)
  if (stored === 'light' || stored === 'dark') {
    return stored
  }

  const prefersDark = window.matchMedia?.('(prefers-color-scheme: dark)')?.matches
  return prefersDark ? 'dark' : 'light'
}

function applyTheme(theme: ThemeMode): void {
  if (typeof document === 'undefined') {
    return
  }

  document.documentElement.dataset.theme = theme
  document.documentElement.classList.toggle('light', theme === 'light')
  document.documentElement.style.colorScheme = theme
}

const restoreTheme = getPreferredTheme()
applyTheme('light')

onBeforeUnmount(() => {
  applyTheme(restoreTheme)
})

const { form, submit: submitForm } = useInertiaForm<LoginFormData>(
  {
    email: '',
    password: '',
    remember: false,
  },
  {
    resetFieldsOnSuccess: ['password'],
    showSuccessToast: false,
    showErrorToast: true,
    errorMessage: 'Неверный email или пароль. Проверьте правильность введенных данных.',
    preserveUrl: true,
    preserveState: true,
  }
)

const showPassword = ref(false)
const errorMap = computed(() => form.errors as Record<string, string | undefined>)
const authError = computed(() => errorMap.value.email ?? errorMap.value.password ?? null)

const baseInputClass = [
  'w-full rounded-2xl border border-transparent bg-[#f2f4f6] py-4 pl-12 pr-4 text-[#191c1e]',
  'placeholder:text-[#7e8a7a]/55 shadow-[inset_0_1px_0_rgba(255,255,255,0.8)] transition-all duration-200',
  'focus:border-[#2f9e5d]/35 focus:bg-white focus:outline-none focus:ring-4 focus:ring-[#2f9e5d]/10',
].join(' ')

const errorInputClass = 'border-[#d95050]/35 bg-[#fffafa] focus:border-[#d95050]/40 focus:ring-[#d95050]/12'

function hasFieldError(field: LoginField): boolean {
  return Boolean(errorMap.value[field])
}

function fieldClass(field: LoginField): string {
  return [baseInputClass, hasFieldError(field) ? errorInputClass : ''].filter(Boolean).join(' ')
}

function submit(): void {
  submitForm('post', route('login'))
}

function togglePasswordVisibility(): void {
  showPassword.value = !showPassword.value
}
</script>

<template>
  <Head title="Вход" />

  <ToastContainer />

  <main class="relative min-h-screen overflow-hidden bg-[#f3f6ef] text-[#191c1e]">
    <div class="pointer-events-none fixed inset-0 -z-10 bg-[#f3f6ef]"></div>
    <div
      class="pointer-events-none fixed inset-0 -z-10 opacity-90"
      style="background-image: radial-gradient(at 0% 0%, rgba(11, 97, 72, 0.05) 0px, transparent 50%), radial-gradient(at 100% 100%, rgba(59, 93, 69, 0.05) 0px, transparent 50%), radial-gradient(at 100% 0%, rgba(47, 123, 96, 0.03) 0px, transparent 50%);"
    ></div>
    <div class="pointer-events-none fixed -top-24 -left-24 h-96 w-96 rounded-full bg-[#0b6148]/5 blur-3xl"></div>
    <div class="pointer-events-none fixed bottom-0 right-0 h-[32rem] w-[32rem] rounded-full bg-[#3b5d45]/5 blur-[100px]"></div>

    <div class="relative mx-auto flex min-h-screen max-w-[1180px] items-center px-4 py-6 sm:px-6 lg:px-8">
      <section
        class="grid w-full overflow-hidden rounded-[2rem] bg-[rgba(255,255,255,0.8)] shadow-[0_24px_70px_rgba(19,32,20,0.14)] ring-1 ring-[rgba(188,200,182,0.42)] backdrop-blur-xl lg:grid-cols-[1.08fr_0.92fr]"
      >
        <aside
          class="relative hidden min-h-[720px] flex-col justify-between overflow-hidden p-12 text-white lg:flex"
          style="background: linear-gradient(135deg, #0b6148 0%, #2f7b60 100%);"
        >
          <div
            class="pointer-events-none absolute inset-0 opacity-30"
            style="background-image: radial-gradient(circle at 20% 20%, rgba(255, 255, 255, 0.18) 0, transparent 28%), radial-gradient(circle at 80% 15%, rgba(255, 255, 255, 0.14) 0, transparent 22%), radial-gradient(circle at 85% 85%, rgba(255, 255, 255, 0.08) 0, transparent 24%);"
          ></div>
          <div class="pointer-events-none absolute inset-0 bg-[linear-gradient(135deg,rgba(255,255,255,0.05),transparent_45%)]"></div>

          <div class="relative z-10">
            <div class="mb-8 flex items-center gap-3">
              <div class="flex h-10 w-10 items-center justify-center rounded-xl bg-white/18 backdrop-blur-md ring-1 ring-white/20">
                <span class="text-sm font-extrabold tracking-[0.22em] text-white">GI</span>
              </div>
              <span class="font-semibold tracking-tight text-[1.35rem]">Greenhouse Intelligence</span>
            </div>

            <h1 class="max-w-xl font-semibold leading-[1.04] tracking-tight text-[clamp(2.8rem,4vw,4.8rem)]">
              Точное земледелие для устойчивого будущего.
            </h1>
            <p class="mt-6 max-w-md text-lg font-medium text-white/78">
              Мониторинг зон в реальном времени с управлением теплицей, автоматизацией и телеметрией в одном интерфейсе.
            </p>
          </div>

          <div class="relative z-10 flex flex-wrap gap-10">
            <div>
              <p class="mb-1 text-[10px] font-bold uppercase tracking-[0.3em] text-white/58">
                Статус
              </p>
              <div class="flex items-center gap-2">
                <span class="h-2 w-2 rounded-full bg-[#aad0b1] shadow-[0_0_0_6px_rgba(170,208,177,0.15)]"></span>
                <span class="text-sm font-semibold">Системы в норме</span>
              </div>
            </div>

            <div>
              <p class="mb-1 text-[10px] font-bold uppercase tracking-[0.3em] text-white/58">
                Активные узлы
              </p>
              <p class="text-sm font-semibold">
                1 248 датчиков
              </p>
            </div>
          </div>

          <div class="pointer-events-none absolute -bottom-20 -right-12 z-0 opacity-10">
            <div class="select-none text-[18rem] font-black leading-none tracking-tight">
              GI
            </div>
          </div>
        </aside>

        <div class="flex flex-col justify-center bg-[rgba(255,255,255,0.92)] px-6 py-10 sm:px-10 lg:px-12 xl:px-16">
          <div class="mb-8 flex justify-center lg:hidden">
            <div class="flex items-center gap-3 text-[#0b6148]">
              <div class="flex h-10 w-10 items-center justify-center rounded-xl bg-[#0b6148] text-white shadow-[0_14px_28px_rgba(11,97,72,0.18)]">
                <span class="text-sm font-extrabold tracking-[0.22em]">GI</span>
              </div>
              <span class="font-semibold tracking-tight text-xl">Greenhouse Intelligence</span>
            </div>
          </div>

          <div class="mx-auto w-full max-w-xl">
            <div class="mb-10">
              <h2 class="font-semibold tracking-tight text-[#191c1e] text-[clamp(2rem,2.4vw,2.75rem)]">
                С возвращением
              </h2>
              <p class="mt-2 text-base font-medium text-[#566456]">
                Войдите в панель управления вашей лабораторией
              </p>
            </div>

            <div
              v-if="props.status"
              class="mb-5 rounded-2xl border border-[rgba(47,158,93,0.22)] bg-[rgba(47,158,93,0.08)] px-4 py-3 text-sm font-medium text-[#2f7c4f]"
              role="status"
            >
              {{ props.status }}
            </div>

            <div
              v-if="authError"
              data-testid="login-error"
              class="mb-5 rounded-2xl border border-[rgba(217,80,80,0.25)] bg-[rgba(217,80,80,0.08)] px-4 py-3 text-sm font-medium text-[#9c3a3a]"
              role="alert"
            >
              {{ authError }}
            </div>

            <form
              data-testid="login-form"
              class="space-y-6"
              @submit.prevent="submit"
            >
              <div class="space-y-2">
                <label
                  class="px-1 text-[10px] font-bold uppercase tracking-[0.3em] text-[#566456]"
                  for="email"
                >
                  Корпоративная почта
                </label>
                <div class="relative group">
                  <div class="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-4">
                    <svg
                      class="h-5 w-5 text-[#7e8a7a] transition-colors group-focus-within:text-[#0b6148]"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        stroke-linecap="round"
                        stroke-linejoin="round"
                        stroke-width="1.9"
                        d="M4 5h16a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1Zm0 2 8 5 8-5"
                      />
                    </svg>
                  </div>
                  <input
                    id="email"
                    v-model="form.email"
                    data-testid="login-email"
                    type="email"
                    autocomplete="username"
                    required
                    autofocus
                    placeholder="name@precisionlabs.org"
                    :class="fieldClass('email')"
                  />
                </div>
              </div>

              <div class="space-y-2">
                <div class="flex items-center justify-between gap-3 px-1">
                  <label
                    class="text-[10px] font-bold uppercase tracking-[0.3em] text-[#566456]"
                    for="password"
                  >
                    Токен безопасности
                  </label>
                  <Link
                    v-if="props.canResetPassword"
                    :href="route('password.request')"
                    class="text-[10px] font-bold uppercase tracking-[0.3em] text-[#0b6148] transition-opacity hover:opacity-80"
                  >
                    Забыл?
                  </Link>
                </div>
                <div class="relative group">
                  <div class="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-4">
                    <svg
                      class="h-5 w-5 text-[#7e8a7a] transition-colors group-focus-within:text-[#0b6148]"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        stroke-linecap="round"
                        stroke-linejoin="round"
                        stroke-width="1.9"
                        d="M7 11V8a5 5 0 0 1 10 0v3m-11 0h12a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1v-8a1 1 0 0 1 1-1Zm5 4v2"
                      />
                    </svg>
                  </div>
                  <input
                    id="password"
                    v-model="form.password"
                    data-testid="login-password"
                    :type="showPassword ? 'text' : 'password'"
                    autocomplete="current-password"
                    required
                    placeholder="••••••••"
                    :class="[fieldClass('password'), 'pr-14']"
                  />
                  <button
                    type="button"
                    class="absolute inset-y-0 right-0 flex items-center px-4 text-[#7e8a7a] transition-colors hover:text-[#0b6148]"
                    :aria-label="showPassword ? 'Скрыть пароль' : 'Показать пароль'"
                    @click="togglePasswordVisibility"
                  >
                    <svg
                      v-if="showPassword"
                      class="h-5 w-5"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        stroke-linecap="round"
                        stroke-linejoin="round"
                        stroke-width="1.9"
                        d="M3 3l18 18M10.58 10.58A2 2 0 0 0 13.4 13.4M9.88 5.08A10.45 10.45 0 0 1 12 4.75c7.5 0 10 7.25 10 7.25a18.1 18.1 0 0 1-4.36 5.32M6.1 6.1A18.06 18.06 0 0 0 2 12s2.5 7.25 10 7.25a10.4 10.4 0 0 0 3.4-.58"
                      />
                    </svg>
                    <svg
                      v-else
                      class="h-5 w-5"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        stroke-linecap="round"
                        stroke-linejoin="round"
                        stroke-width="1.9"
                        d="M2.5 12s3.25-7 9.5-7 9.5 7 9.5 7-3.25 7-9.5 7-9.5-7-9.5-7Zm9.5 3.5A3.5 3.5 0 1 0 8.5 12 3.5 3.5 0 0 0 12 15.5Z"
                      />
                    </svg>
                  </button>
                </div>
              </div>

              <div class="flex items-center">
                <label class="flex items-center gap-3">
                  <input
                    v-model="form.remember"
                    type="checkbox"
                    class="h-4 w-4 rounded border border-[rgba(120,140,118,0.55)] bg-white text-[#0b6148] focus:ring-2 focus:ring-[#2f9e5d]/20"
                    name="remember"
                  />
                  <span class="text-sm text-[#566456]">Запомнить меня</span>
                </label>
              </div>

              <button
                type="submit"
                data-testid="login-submit"
                class="inline-flex w-full items-center justify-center gap-3 rounded-2xl bg-[linear-gradient(135deg,#0b6148_0%,#2f7b60_100%)] px-6 py-4 font-semibold text-white shadow-[0_18px_40px_rgba(11,97,72,0.22)] transition-all hover:-translate-y-0.5 hover:shadow-[0_22px_48px_rgba(11,97,72,0.28)] active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-60"
                :disabled="form.processing"
              >
                <span>Войти в систему</span>
                <svg
                  class="h-5 w-5"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    stroke-width="2"
                    d="M5 12h14m-6-6 6 6-6 6"
                  />
                </svg>
              </button>

              <p class="text-center text-sm text-[#566456]">
                Нет аккаунта?
                <Link
                  :href="route('register')"
                  class="font-semibold text-[#0b6148] underline decoration-2 underline-offset-4 transition-opacity hover:opacity-80"
                >
                  Зарегистрироваться
                </Link>
              </p>
            </form>
          </div>
        </div>
      </section>
    </div>
  </main>
</template>
