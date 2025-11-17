<template>
  <div class="rounded-xl border border-neutral-800 overflow-hidden">
    <table class="min-w-full text-sm">
      <thead class="bg-neutral-900 text-neutral-300">
        <tr>
          <th v-for="(h, i) in headers" :key="i" class="px-3 py-2 text-left font-medium border-b border-neutral-800">
            {{ h }}
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, ri) in rows" :key="ri" class="odd:bg-neutral-950 even:bg-neutral-925">
          <td v-for="(cell, ci) in row" :key="ci" class="px-3 py-2 border-b border-neutral-900">
            <slot :name="`cell-${ci}`" :value="cell">{{ cell }}</slot>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
defineProps({
  headers: { type: Array, default: () => [] },
  rows: { type: Array, default: () => [] },
})
</script>

