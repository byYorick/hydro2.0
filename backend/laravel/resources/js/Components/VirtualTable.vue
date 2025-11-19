<template>
  <RecycleScroller
    class="virtual-table"
    :items="items"
    :item-size="itemSize"
    key-field="id"
    v-slot="{ item, index }"
  >
    <slot :item="item" :index="index" />
  </RecycleScroller>
</template>

<script setup lang="ts">
import { RecycleScroller } from 'vue-virtual-scroller'
import 'vue-virtual-scroller/dist/vue-virtual-scroller.css'

interface Props {
  items: unknown[]
  itemSize?: number
}

withDefaults(defineProps<Props>(), {
  itemSize: 44
})
</script>

<style scoped>
.virtual-table {
  height: 100%;
}
</style>

