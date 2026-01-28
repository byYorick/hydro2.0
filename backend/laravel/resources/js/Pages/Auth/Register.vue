<script setup lang="ts">
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

interface RegisterFormData {
    name: string
    email: string
    password: string
    password_confirmation: string
    [key: string]: any
}

const { form, submit: submitForm } = useInertiaForm<RegisterFormData>(
    {
        name: '',
        email: '',
        password: '',
        password_confirmation: '',
    },
    {
        resetFieldsOnSuccess: ['password', 'password_confirmation'],
        showSuccessToast: false, // Auth формы обычно не показывают Toast
        showErrorToast: false,
    }
);

const submit = (): void => {
    submitForm('post', route('register'));
};
</script>

<template>
  <GuestLayout>
    <Head title="Регистрация" />

    <form @submit.prevent="submit">
      <div>
        <InputLabel
          for="name"
          value="Имя"
        />

        <TextInput
          id="name"
          v-model="form.name"
          type="text"
          class="mt-1 block w-full"
          required
          autofocus
          autocomplete="name"
        />

        <InputError
          class="mt-2"
          :message="(form.errors as any).name"
        />
      </div>

      <div class="mt-4">
        <InputLabel
          for="email"
          value="Email"
        />

        <TextInput
          id="email"
          v-model="form.email"
          type="email"
          class="mt-1 block w-full"
          required
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
          class="mt-1 block w-full"
          required
          autocomplete="new-password"
        />

        <InputError
          class="mt-2"
          :message="(form.errors as any).password"
        />
      </div>

      <div class="mt-4">
        <InputLabel
          for="password_confirmation"
          value="Подтвердите пароль"
        />

        <TextInput
          id="password_confirmation"
          v-model="form.password_confirmation"
          type="password"
          class="mt-1 block w-full"
          required
          autocomplete="new-password"
        />

        <InputError
          class="mt-2"
          :message="(form.errors as any).password_confirmation"
        />
      </div>

      <div class="mt-4 flex items-center justify-between">
        <Link
          :href="route('login')"
          class="rounded-md text-sm text-[color:var(--text-muted)] underline hover:text-[color:var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[color:var(--focus-ring)] focus:ring-offset-2"
        >
          Уже зарегистрированы? Войти
        </Link>

        <Button
          variant="primary"
          class="ms-4"
          :class="{ 'opacity-25': form.processing }"
          :disabled="form.processing"
        >
          Зарегистрироваться
        </Button>
      </div>
    </form>
  </GuestLayout>
</template>
