<script setup>
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import DeleteUserForm from './Partials/DeleteUserForm.vue'
import UpdatePasswordForm from './Partials/UpdatePasswordForm.vue'
import UpdateProfileInformationForm from './Partials/UpdateProfileInformationForm.vue'
import { Head } from '@inertiajs/vue3'

defineProps({
    mustVerifyEmail: {
        type: Boolean,
    },
    status: {
        type: String,
    },
})
</script>

<template>
  <Head title="Профиль" />

  <AppLayout>
    <div class="max-w-4xl mx-auto space-y-4">
      <Card>
        <h2 class="text-base font-semibold text-neutral-100 mb-4">Общая информация</h2>
                    <UpdateProfileInformationForm
                        :must-verify-email="mustVerifyEmail"
                        :status="status"
                        class="max-w-xl"
                    />
      </Card>

      <Card>
        <h2 class="text-base font-semibold text-neutral-100 mb-4">Безопасность</h2>
                    <UpdatePasswordForm class="max-w-xl" />
      </Card>

      <Card>
        <h2 class="text-base font-semibold text-neutral-100 mb-4">Опасная зона</h2>
                    <DeleteUserForm class="max-w-xl" />
      </Card>
                </div>
  </AppLayout>
</template>
