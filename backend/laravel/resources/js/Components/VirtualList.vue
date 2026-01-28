<template>
  <RecycleScroller
    v-slot="{ item, index }"
    class="virtual-list"
    :items="items"
    :item-size="itemSize"
    :key-field="keyField"
  >
    <slot
      :item="item"
      :index="index"
    ></slot>
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

