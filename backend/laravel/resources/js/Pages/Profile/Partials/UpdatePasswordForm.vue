<script setup lang="ts">
import InputError from '@/Components/InputError.vue';
import InputLabel from '@/Components/InputLabel.vue';
import Button from '@/Components/Button.vue';
import TextInput from '@/Components/TextInput.vue';
import { useInertiaForm } from '@/composables/useInertiaForm';
import { route } from '@/utils/route';
import { ref } from 'vue';

const passwordInput = ref(null);
const currentPasswordInput = ref(null);

interface UpdatePasswordFormData {
    current_password: string;
    password: string;
    password_confirmation: string;
}

const { form, submit: submitForm } = useInertiaForm<UpdatePasswordFormData>(
    {
        current_password: '',
        password: '',
        password_confirmation: '',
    },
    {
        resetOnSuccess: true,
        successMessage: 'Пароль успешно обновлен',
        preserveScroll: true,
        onError: (errors) => {
            if (errors.password) {
                form.reset('password', 'password_confirmation');
                passwordInput.value?.focus();
            }
            if (errors.current_password) {
                form.reset('current_password');
                currentPasswordInput.value?.focus();
            }
        },
    }
);

const updatePassword = () => {
    submitForm('put', route('password.update'));
};
</script>

<template>
    <section>
        <header>
            <h2 class="text-lg font-medium text-neutral-100">
                Изменение пароля
            </h2>

            <p class="mt-1 text-sm text-neutral-400">
                Убедитесь, что ваш аккаунт использует длинный, случайный пароль для обеспечения безопасности.
            </p>
        </header>

        <form @submit.prevent="updatePassword" class="mt-6 space-y-6">
            <div>
                <InputLabel for="current_password" value="Текущий пароль" />

                <TextInput
                    id="current_password"
                    ref="currentPasswordInput"
                    v-model="form.current_password"
                    type="password"
                    class="mt-1 block w-full"
                    autocomplete="current-password"
                />

                <InputError
                    :message="form.errors.current_password"
                    class="mt-2"
                />
            </div>

            <div>
                <InputLabel for="password" value="Новый пароль" />

                <TextInput
                    id="password"
                    ref="passwordInput"
                    v-model="form.password"
                    type="password"
                    class="mt-1 block w-full"
                    autocomplete="new-password"
                />

                <InputError :message="form.errors.password" class="mt-2" />
            </div>

            <div>
                <InputLabel
                    for="password_confirmation"
                    value="Подтвердите пароль"
                />

                <TextInput
                    id="password_confirmation"
                    v-model="form.password_confirmation"
                    type="password"
                    class="mt-1 block w-full"
                    autocomplete="new-password"
                />

                <InputError
                    :message="form.errors.password_confirmation"
                    class="mt-2"
                />
            </div>

            <div class="flex items-center gap-4">
                <Button variant="primary" :disabled="form.processing">Сохранить</Button>

                <Transition
                    enter-active-class="transition ease-in-out"
                    enter-from-class="opacity-0"
                    leave-active-class="transition ease-in-out"
                    leave-to-class="opacity-0"
                >
                    <p
                        v-if="form.recentlySuccessful"
                        class="text-sm text-neutral-400"
                    >
                        Сохранено.
                    </p>
                </Transition>
            </div>
        </form>
    </section>
</template>
