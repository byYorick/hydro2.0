<script setup lang="ts">
import InputError from '@/Components/InputError.vue';
import InputLabel from '@/Components/InputLabel.vue';
import Button from '@/Components/Button.vue';
import TextInput from '@/Components/TextInput.vue';
import { Link, usePage } from '@inertiajs/vue3';
import { useInertiaForm } from '@/composables/useInertiaForm';
import { route } from '@/utils/route';

defineProps({
    mustVerifyEmail: {
        type: Boolean,
    },
    status: {
        type: String,
    },
});

const user = usePage().props.auth.user;

interface UpdateProfileInformationFormData {
    name: string;
    email: string;
}

const { form, submit: submitForm } = useInertiaForm<UpdateProfileInformationFormData>(
    {
        name: user.name,
        email: user.email,
    },
    {
        successMessage: 'Профиль успешно обновлен',
        preserveScroll: true,
    }
);

const submit = () => {
    submitForm('patch', route('profile.update'));
};
</script>

<template>
    <section>
        <header>
            <h2 class="text-lg font-medium text-neutral-100">
                Информация профиля
            </h2>

            <p class="mt-1 text-sm text-neutral-400">
                Обновите информацию о вашем профиле и адрес электронной почты.
            </p>
        </header>

        <form
            @submit.prevent="submit"
            class="mt-6 space-y-6"
        >
            <div>
                <InputLabel for="name" value="Имя" />

                <TextInput
                    id="name"
                    type="text"
                    class="mt-1 block w-full"
                    v-model="form.name"
                    required
                    autofocus
                    autocomplete="name"
                />

                <InputError class="mt-2" :message="form.errors.name" />
            </div>

            <div>
                <InputLabel for="email" value="Email" />

                <TextInput
                    id="email"
                    type="email"
                    class="mt-1 block w-full"
                    v-model="form.email"
                    required
                    autocomplete="username"
                />

                <InputError class="mt-2" :message="form.errors.email" />
            </div>

            <div v-if="mustVerifyEmail && user.email_verified_at === null">
                <p class="mt-2 text-sm text-neutral-400">
                    Ваш адрес электронной почты не подтвержден.
                    <Link
                        :href="route('verification.send')"
                        method="post"
                        as="button"
                        class="rounded-md text-sm text-neutral-300 underline hover:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
                    >
                        Нажмите здесь, чтобы повторно отправить письмо с подтверждением.
                    </Link>
                </p>

                <div
                    v-show="status === 'verification-link-sent'"
                    class="mt-2 text-sm font-medium text-emerald-400"
                >
                    Новое письмо с подтверждением отправлено на ваш адрес электронной почты.
                </div>
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
