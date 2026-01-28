<template>
  <RecycleScroller
    v-slot="{ item, index }"
    class="virtual-table"
    :class="containerClass"
    :items="items"
    :item-size="itemSize"
    :key-field="keyField"
    :tag="tag"
    :item-tag="itemTag"
  >
    <slot
      :item="item"
      :index="index"
    ></slot>
  </RecycleScroller>
</template>

<script setup lang="ts">
// @ts-ignore
import { RecycleScroller } from 'vue-virtual-scroller'
import 'vue-virtual-scroller/dist/vue-virtual-scroller.css'

interface Props {
  items: unknown[]
  itemSize?: number
  keyField?: string
  tag?: string
  itemTag?: string
  containerClass?: string
}

withDefaults(defineProps<Props>(), {
  itemSize: 44,
  keyField: 'id',
  tag: 'div',
  itemTag: 'div',
  containerClass: '',
})
</script>

<style scoped>
.virtual-table {
  height: 100%;
  width: 100%;
}
</style>
