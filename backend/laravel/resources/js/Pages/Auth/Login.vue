<script setup lang="ts">
// Удалены неиспользуемые импорты
import Checkbox from '@/Components/Checkbox.vue';
// @ts-ignore
import GuestLayout from '@/Layouts/GuestLayout.vue';
import InputError from '@/Components/InputError.vue';
import InputLabel from '@/Components/InputLabel.vue';
import Button from '@/Components/Button.vue';
import TextInput from '@/Components/TextInput.vue';
import { Head, Link } from '@inertiajs/vue3';
// Импорт route из утилиты
import { route } from '@/utils/route';
import { useInertiaForm } from '@/composables/useInertiaForm';

interface Props {
    canResetPassword?: boolean
    status?: string
}

defineProps<Props>()

interface LoginFormData {
    email: string
    password: string
    remember: boolean
    [key: string]: any
}

const { form, submit: submitForm } = useInertiaForm<LoginFormData>(
    {
        email: '',
        password: '',
        remember: false,
    },
    {
        resetFieldsOnSuccess: ['password'],
        showSuccessToast: false, // Auth формы обычно не показывают Toast при успехе
        showErrorToast: true, // Показываем toast при ошибке аутентификации
        errorMessage: 'Неверный email или пароль. Проверьте правильность введенных данных.',
        preserveUrl: true, // Сохраняем позицию прокрутки при ошибке
        preserveState: true, // Сохраняем состояние формы при ошибке
    }
);

const submit = (): void => {
    submitForm('post', route('login'));
    // preserveUrl и preserveState уже настроены в useInertiaForm
    // Toast уведомления обрабатываются автоматически
    // Форма остается на странице логина при ошибке валидации
};
</script>

<template>
  <GuestLayout>
    <Head title="Вход" />

    <!-- Сообщение об успехе (например, после регистрации или сброса пароля) -->
    <div
      v-if="status"
      class="mb-4 rounded-md bg-[color:var(--badge-success-bg)] p-4 text-sm font-medium text-[color:var(--badge-success-text)] border border-[color:var(--badge-success-border)]"
    >
      {{ status }}
    </div>

    <!-- Ошибки валидации показываются под полями и в toast -->
    <!-- Основные ошибки аутентификации показываются через toast -->
    <!-- Блок ошибки убран, чтобы избежать дублирования с toast -->

    <form
      data-testid="login-form"
      @submit.prevent="submit"
    >
      <div>
        <InputLabel
          for="email"
          value="Email"
        />

        <TextInput
          id="email"
          v-model="form.email"
          type="email"
          data-testid="login-email"
          :class="[
            'mt-1 block w-full',
            (form.errors as any).email
              ? 'border-[color:var(--accent-red)] focus:border-[color:var(--accent-red)] focus:ring-[color:var(--accent-red)]' 
              : ''
          ]"
          required
          autofocus
          autocomplete="username"
        />

        <InputError
          class="mt-2"
          :message="(form.errors as any).email"
        />
      </div>

      <div class="mt-4">
        <InputLabel
          for="password"
          value="Пароль"
        />

        <TextInput
          id="password"
          v-model="form.password"
          type="password"
          data-testid="login-password"
          :class="[
            'mt-1 block w-full',
            (form.errors as any).password
              ? 'border-[color:var(--accent-red)] focus:border-[color:var(--accent-red)] focus:ring-[color:var(--accent-red)]' 
              : ''
          ]"
          required
          autocomplete="current-password"
        />

        <InputError
          class="mt-2"
          :message="(form.errors as any).password"
        />
      </div>

      <div class="mt-4 block">
        <label class="flex items-center">
          <Checkbox
            v-model:checked="form.remember"
            name="remember"
          />
          <span class="ms-2 text-sm text-[color:var(--text-muted)]">Запомнить меня</span>
        </label>
      </div>

      <div class="mt-4 flex items-center justify-between">
        <Link
          :href="route('register')"
          class="rounded-md text-sm text-[color:var(--text-muted)] underline hover:text-[color:var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[color:var(--focus-ring)] focus:ring-offset-2"
        >
          Нет аккаунта? Зарегистрироваться
        </Link>

        <div class="flex items-center gap-4">
          <Link
            v-if="canResetPassword"
            :href="route('password.request')"
            class="rounded-md text-sm text-[color:var(--text-muted)] underline hover:text-[color:var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[color:var(--focus-ring)] focus:ring-offset-2"
          >
            Забыли пароль?
          </Link>

          <Button 
            variant="primary"
            data-testid="login-submit"
            class="ms-4"
            :class="{ 'opacity-25': form.processing }"
            :disabled="form.processing"
          >
            Войти
          </Button>
        </div>
      </div>
    </form>
  </GuestLayout>
</template>
