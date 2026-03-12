<template>
  <RecycleScroller
    class="virtual-list"
    :items="items"
    :item-size="itemSize"
    :key-field="keyField"
    v-slot="{ item, index }"
  >
    <slot :item="item" :index="index" />
  </RecycleScroller>
</template>

<script setup lang="ts">
interface Props {
  items: unknown[]
  itemSize?: number
  keyField?: string
}

withDefaults(defineProps<Props>(), {
  itemSize: 44,
  keyField: 'id'
})
</script>

<style scoped>
.virtual-list {
  height: 100%;
}
</style>

