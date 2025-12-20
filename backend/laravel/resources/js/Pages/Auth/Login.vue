<script setup lang="ts">
import { computed } from 'vue';
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

// Проверяем, есть ли ошибки аутентификации
const hasAuthError = computed(() => {
    return !!(form.errors.email || form.errors.password);
});

// Получаем общее сообщение об ошибке
const authErrorMessage = computed(() => {
    if (form.errors.email) {
        return form.errors.email;
    }
    if (form.errors.password) {
        return form.errors.password;
    }
    return null;
});
</script>

<template>
    <GuestLayout>
        <Head title="Вход" />

        <div v-if="status" class="mb-4 rounded-md bg-[color:var(--badge-success-bg)] p-4 text-sm font-medium text-[color:var(--badge-success-text)] border border-[color:var(--badge-success-border)]">
            {{ status }}
        </div>

        <div 
            v-if="hasAuthError && authErrorMessage" 
            data-testid="login-error"
            class="mb-4 rounded-md bg-[color:var(--badge-danger-bg)] p-4 text-sm font-medium text-[color:var(--badge-danger-text)] border border-[color:var(--badge-danger-border)]"
        >
            {{ authErrorMessage }}
        </div>

        <form @submit.prevent="submit" data-testid="login-form">
            <div>
                <InputLabel for="email" value="Email" />

                <TextInput
                    id="email"
                    type="email"
                    data-testid="login-email"
                    :class="[
                        'mt-1 block w-full',
                        form.errors.email 
                            ? 'border-[color:var(--accent-red)] focus:border-[color:var(--accent-red)] focus:ring-[color:var(--accent-red)]' 
                            : ''
                    ]"
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
                    data-testid="login-password"
                    :class="[
                        'mt-1 block w-full',
                        form.errors.password 
                            ? 'border-[color:var(--accent-red)] focus:border-[color:var(--accent-red)] focus:ring-[color:var(--accent-red)]' 
                            : ''
                    ]"
                    v-model="form.password"
                    required
                    autocomplete="current-password"
                />

                <InputError class="mt-2" :message="form.errors.password" />
            </div>

            <div class="mt-4 block">
                <label class="flex items-center">
                    <Checkbox name="remember" v-model:checked="form.remember" />
                    <span class="ms-2 text-sm text-[color:var(--text-muted)]"
                        >Запомнить меня</span
                    >
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
