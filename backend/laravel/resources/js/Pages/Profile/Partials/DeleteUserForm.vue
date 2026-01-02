<script setup lang="ts">
import Button from '@/Components/Button.vue';
import InputError from '@/Components/InputError.vue';
import InputLabel from '@/Components/InputLabel.vue';
import Modal from '@/Components/Modal.vue';
import TextInput from '@/Components/TextInput.vue';
import { useInertiaForm } from '@/composables/useInertiaForm';
import { route } from '@/utils/route';
import { nextTick, ref } from 'vue';

const confirmingUserDeletion = ref(false);
const passwordInput = ref(null);

interface DeleteUserFormData {
    password: string;
    [key: string]: any;
}

const { form, submit: submitForm } = useInertiaForm<DeleteUserFormData>(
    {
        password: '',
    },
    {
        preserveUrl: true,
        showSuccessToast: false, // Удаление аккаунта редиректит, Toast не нужен
        showErrorToast: false,
        onSuccess: () => closeModal(),
        onError: () => passwordInput.value?.focus(),
        resetOnSuccess: true,
    }
);

const confirmUserDeletion = () => {
    confirmingUserDeletion.value = true;

    nextTick(() => passwordInput.value?.focus());
};

const deleteUser = () => {
    submitForm('delete', route('profile.destroy'));
};

const closeModal = () => {
    confirmingUserDeletion.value = false;

    form.clearErrors();
    form.reset();
};
</script>

<template>
    <section class="space-y-6">
        <header>
            <h2 class="text-lg font-medium text-[color:var(--text-primary)]">
                Удаление аккаунта
            </h2>

            <p class="mt-1 text-sm text-[color:var(--text-muted)]">
                После удаления аккаунта все его ресурсы и данные будут безвозвратно удалены. 
                Перед удалением аккаунта, пожалуйста, загрузите все данные или информацию, 
                которую вы хотите сохранить.
            </p>
        </header>

        <Button variant="danger" @click="confirmUserDeletion">Удалить аккаунт</Button>

        <Modal :show="confirmingUserDeletion" @close="closeModal">
            <div class="p-6">
                <h2
                    class="text-lg font-medium text-[color:var(--text-primary)]"
                >
                    Вы уверены, что хотите удалить свой аккаунт?
                </h2>

                <p class="mt-1 text-sm text-[color:var(--text-muted)]">
                    После удаления аккаунта все его ресурсы и данные будут безвозвратно удалены. 
                    Пожалуйста, введите ваш пароль для подтверждения удаления аккаунта.
                </p>

                <div class="mt-6">
                    <InputLabel
                        for="password"
                        value="Пароль"
                        class="sr-only"
                    />

                    <TextInput
                        id="password"
                        ref="passwordInput"
                        v-model="form.password"
                        type="password"
                        class="mt-1 block w-3/4"
                        placeholder="Пароль"
                        @keyup.enter="deleteUser"
                    />

                    <InputError :message="form.errors.password" class="mt-2" />
                </div>

                <div class="mt-6 flex justify-end">
                    <Button variant="secondary" @click="closeModal">
                        Отмена
                    </Button>

                    <Button variant="danger"
                        class="ms-3"
                        :class="{ 'opacity-25': form.processing }"
                        :disabled="form.processing"
                        @click="deleteUser"
                    >
                        Удалить аккаунт
                    </Button>
                </div>
            </div>
        </Modal>
    </section>
</template>
