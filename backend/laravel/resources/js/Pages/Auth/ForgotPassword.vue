<script setup lang="ts">
import GuestLayout from '@/Layouts/GuestLayout.vue';
import InputError from '@/Components/InputError.vue';
import InputLabel from '@/Components/InputLabel.vue';
import Button from '@/Components/Button.vue';
import TextInput from '@/Components/TextInput.vue';
import { Head } from '@inertiajs/vue3';
// ИСПРАВЛЕНО: Импорт route из утилиты
import { route } from '@/utils/route';
import { useInertiaForm } from '@/composables/useInertiaForm';

defineProps({
    status: {
        type: String,
    },
});

interface ForgotPasswordFormData {
    email: string;
}

const { form, submit: submitForm } = useInertiaForm<ForgotPasswordFormData>(
    {
        email: '',
    },
    {
        showSuccessToast: false,
        showErrorToast: false,
    }
);

const submit = () => {
    submitForm('post', route('password.email'));
};
</script>

<template>
    <GuestLayout>
        <Head title="Forgot Password" />

        <div class="mb-4 text-sm text-gray-600">
            Forgot your password? No problem. Just let us know your email
            address and we will email you a password reset link that will allow
            you to choose a new one.
        </div>

        <div
            v-if="status"
            class="mb-4 text-sm font-medium text-green-600"
        >
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

            <div class="mt-4 flex items-center justify-end">
                    <Button variant="primary"
                    :class="{ 'opacity-25': form.processing }"
                    :disabled="form.processing"
                >
                    Email Password Reset Link
                    </Button>
            </div>
        </form>
    </GuestLayout>
</template>
