<script setup lang="ts">
import Checkbox from '@/Components/Checkbox.vue';
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
}

const { form, submit: submitForm } = useInertiaForm<LoginFormData>(
    {
        email: '',
        password: '',
        remember: false,
    },
    {
        resetFieldsOnSuccess: ['password'],
        showSuccessToast: false, // Auth формы обычно не показывают Toast
        showErrorToast: false,
    }
);

const submit = (): void => {
    submitForm('post', route('login'));
};
</script>

<template>
    <GuestLayout>
        <Head title="Вход" />

        <div v-if="status" class="mb-4 text-sm font-medium text-green-600">
            {{ status }}
        </div>

        <form @submit.prevent="submit">
            <div>
                <InputLabel for="email" value="Email" />

                <TextInput
                    id="email"
                    type="email"
                    class="mt-1 block w-full"
                    v-model="form.email"
                    required
                    autofocus
                    autocomplete="username"
                />

                <InputError class="mt-2" :message="form.errors.email" />
            </div>

            <div class="mt-4">
                <InputLabel for="password" value="Пароль" />

                <TextInput
                    id="password"
                    type="password"
                    class="mt-1 block w-full"
                    v-model="form.password"
                    required
                    autocomplete="current-password"
                />

                <InputError class="mt-2" :message="form.errors.password" />
            </div>

            <div class="mt-4 block">
                <label class="flex items-center">
                    <Checkbox name="remember" v-model:checked="form.remember" />
                    <span class="ms-2 text-sm text-gray-600"
                        >Запомнить меня</span
                    >
                </label>
            </div>

            <div class="mt-4 flex items-center justify-between">
                <Link
                    :href="route('register')"
                    class="rounded-md text-sm text-gray-600 underline hover:text-gray-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
                >
                    Нет аккаунта? Зарегистрироваться
                </Link>

                <div class="flex items-center gap-4">
                    <Link
                        v-if="canResetPassword"
                        :href="route('password.request')"
                        class="rounded-md text-sm text-gray-600 underline hover:text-gray-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
                    >
                        Забыли пароль?
                    </Link>

                    <Button variant="primary"
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
