<template>
  <section
    class="grid gap-4 items-start"
    :class="rightColClass"
  >
    <div class="flex flex-col gap-3">
      <ShellCard title="Теплица">
        <template #actions>
          <Chip
            v-if="selectedGreenhouseId"
            tone="growth"
          >
            <template #icon>
              <span class="inline-block w-1.5 h-1.5 rounded-full bg-growth"></span>
            </template>
            выбрана
          </Chip>
          <Chip
            v-else
            tone="warn"
          >
            не выбрана
          </Chip>
        </template>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Field
            label="Теплица"
            required
          >
            <Select
              :model-value="selectedGreenhouseId ?? ''"
              :options="greenhouseOptions"
              placeholder="— выберите —"
              @update:model-value="(v: string) => onGreenhouseSelect(v ? Number(v) : null)"
            />
          </Field>
          <Field label="Тип конструкции">
            <Select
              :model-value="(selectedGreenhouse?.type as string | undefined) ?? ''"
              :options="typeOptions"
              placeholder="не указан"
              disabled
            />
          </Field>

          <div
            v-if="selectedGreenhouse"
            class="md:col-span-2 grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2 border-t border-[var(--border-muted)]"
          >
            <Stat
              label="UID"
              :value="selectedGreenhouse.uid ?? '—'"
              mono
            />
            <Stat
              label="Тип"
              :value="selectedGreenhouse.type ?? '—'"
            />
            <Stat
              label="ID"
              :value="selectedGreenhouse.id"
              mono
            />
            <Stat
              label="Зон"
              :value="zonesInSelectedGh.length"
              mono
              tone="brand"
            />
          </div>
        </div>

        <div class="flex items-center gap-2 pt-3 mt-3 border-t border-[var(--border-muted)]">
          <span class="text-xs text-[var(--text-dim)]">Нужна новая теплица?</span>
          <Link
            :href="greenhousesIndexHref"
            class="inline-flex items-center gap-1 px-2 py-1 text-xs rounded-md border border-[var(--border-muted)] bg-[var(--bg-surface)] text-[var(--text-primary)] hover:border-[var(--border-strong)]"
          >
            → Перейти на /greenhouses
          </Link>
        </div>
      </ShellCard>

      <ShellCard
        v-if="selectedGreenhouseId"
        title="Зона"
      >
        <template #actions>
          <Button
            size="sm"
            :variant="zoneMode === 'select' ? 'primary' : 'secondary'"
            @click="zoneMode = 'select'"
          >
            Выбрать
          </Button>
          <Button
            size="sm"
            :variant="zoneMode === 'create' ? 'primary' : 'secondary'"
            @click="zoneMode = 'create'"
          >
            + Создать
          </Button>
        </template>

        <div
          v-if="zoneMode === 'select'"
          class="flex flex-col gap-3"
        >
          <ZoneList
            :zones="zonesInSelectedGh"
            :active-id="modelValue ?? null"
            @pick="(id) => emit('update:modelValue', id)"
          />
        </div>

        <div
          v-else
          class="grid grid-cols-1 md:grid-cols-2 gap-3"
        >
          <Field
            label="Название зоны"
            required
          >
            <TextInput
              v-model="newZoneName"
              placeholder="Zone A"
              maxlength="120"
            />
          </Field>
          <Field label="Описание">
            <TextInput
              v-model="newZoneDescription"
              placeholder="Front launch zone"
              maxlength="255"
            />
          </Field>
          <div class="md:col-span-2 flex items-center justify-end gap-2">
            <Button
              size="sm"
              variant="secondary"
              @click="zoneMode = 'select'"
            >
              Отмена
            </Button>
            <Button
              size="sm"
              variant="primary"
              :disabled="!newZoneName.trim() || creatingZone"
              @click="createZone"
            >
              {{ creatingZone ? 'Создание…' : 'Создать зону' }}
            </Button>
          </div>
        </div>
      </ShellCard>
    </div>

    <aside class="flex flex-col gap-3 lg:sticky lg:top-[108px] lg:self-start">
      <Hint :show="showHints">
        Теплица — физическая группа зон с общим MQTT-бриджем и пулом ESP32-узлов.
        Зона — минимальная единица автоматизации: свой grow-cycle, рецепт, контуры
        и PID. Здесь выбирается контейнер для запуска.
      </Hint>

      <ShellCard title="MQTT / Bridge">
        <KV
          :rows="[
            ['mqtt-bridge', '9000'],
            ['history-logger', '9300'],
            ['automation-engine', '9405'],
          ]"
        />
      </ShellCard>
    </aside>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Link } from '@inertiajs/vue3'
import { api } from '@/services/api'
import { useToast } from '@/composables/useToast'
import { useLaunchPreferences } from '@/composables/useLaunchPreferences'
import Button from '@/Components/Button.vue'
import TextInput from '@/Components/TextInput.vue'
import {
  Field,
  Select,
  Chip,
  Stat,
  Hint,
  KV,
} from '@/Components/Shared/Primitives'
import ShellCard from '@/Components/Launch/Shell/ShellCard.vue'
import ZoneList, { type ZoneListItem } from '@/Components/Launch/Zone/ZoneList.vue'

interface GreenhouseRecord {
  id: number
  uid?: string
  name: string
  type?: string | null
}
interface ActiveGrowCyclePreview {
  plant?: { name?: string | null } | null
  currentPhase?: { name?: string | null } | null
  active_grow_day?: number | null
}

interface ZoneRecord {
  id: number
  name: string
  description?: string | null
  status?: string | null
  greenhouse_id?: number | null
  active_grow_cycle?: ActiveGrowCyclePreview | null
  activeGrowCycle?: ActiveGrowCyclePreview | null
}

const props = defineProps<{ modelValue?: number | null }>()
const emit = defineEmits<{ (e: 'update:modelValue', id: number): void }>()

const { showToast } = useToast()
const { showHints } = useLaunchPreferences()

const greenhouses = ref<GreenhouseRecord[]>([])
const zones = ref<ZoneRecord[]>([])
const selectedGreenhouseId = ref<number | null>(null)
const zoneMode = ref<'select' | 'create'>('select')
const newZoneName = ref('')
const newZoneDescription = ref('')
const creatingZone = ref(false)

const greenhouseOptions = computed(() =>
  greenhouses.value.map((g) => ({
    value: g.id,
    label: g.uid ? `${g.uid.toUpperCase()} · ${g.name}` : g.name,
  })),
)

const selectedGreenhouse = computed<GreenhouseRecord | null>(
  () => greenhouses.value.find((g) => g.id === selectedGreenhouseId.value) ?? null,
)

const zonesInSelectedGh = computed<ZoneListItem[]>(() =>
  zones.value
    .filter((z) => z.greenhouse_id === selectedGreenhouseId.value)
    .map((z) => {
      const cycle = z.active_grow_cycle ?? z.activeGrowCycle ?? null
      const phaseName = cycle?.currentPhase?.name ?? null
      const day = cycle?.active_grow_day != null ? `d${cycle.active_grow_day}` : null
      const stage = phaseName && day ? `${phaseName} ${day}` : (phaseName ?? day)
      return {
        id: z.id,
        name: z.name,
        description: z.description ?? null,
        status: z.status ?? null,
        plant: cycle?.plant?.name ?? null,
        stage,
      }
    }),
)

const typeOptions = computed(() =>
  selectedGreenhouse.value?.type ? [selectedGreenhouse.value.type] : ['—'],
)

const greenhousesIndexHref = computed(() => '/greenhouses')

const rightColClass = computed(() => 'lg:[grid-template-columns:1fr_320px]')

function toArray<T>(value: unknown): T[] {
  if (Array.isArray(value)) return value as T[]
  if (value && typeof value === 'object') {
    const obj = value as { data?: unknown }
    if (Array.isArray(obj.data)) return obj.data as T[]
  }
  return []
}

async function loadAll(): Promise<void> {
  try {
    const [ghList, zoneList] = await Promise.all([
      api.greenhouses.list(),
      api.zones.list(),
    ])
    greenhouses.value = toArray<GreenhouseRecord>(ghList)
    zones.value = toArray<ZoneRecord>(zoneList)

    const initialZoneId = props.modelValue
    if (initialZoneId) {
      const zone = zones.value.find((z) => z.id === initialZoneId)
      if (zone?.greenhouse_id) {
        selectedGreenhouseId.value = zone.greenhouse_id
      }
    } else if (greenhouses.value.length === 1) {
      selectedGreenhouseId.value = greenhouses.value[0].id
    }
  } catch (error) {
    showToast((error as Error).message || 'Ошибка загрузки теплиц/зон', 'error')
  }
}

onMounted(loadAll)

watch(
  () => props.modelValue,
  (zoneId) => {
    if (!zoneId) return
    const zone = zones.value.find((z) => z.id === zoneId)
    if (zone?.greenhouse_id && zone.greenhouse_id !== selectedGreenhouseId.value) {
      selectedGreenhouseId.value = zone.greenhouse_id
    }
  },
)

function onGreenhouseSelect(id: number | null): void {
  selectedGreenhouseId.value = id
  // Если текущая выбранная зона больше не принадлежит выбранной теплице — сбрасываем.
  if (props.modelValue) {
    const current = zones.value.find((z) => z.id === props.modelValue)
    if (current?.greenhouse_id !== id) {
      emit('update:modelValue', 0)
    }
  }
  zoneMode.value = 'select'
}

async function createZone(): Promise<void> {
  if (!selectedGreenhouseId.value) return
  const name = newZoneName.value.trim()
  if (!name) return
  creatingZone.value = true
  try {
    const created = (await api.zones.create({
      name,
      description: newZoneDescription.value.trim() || undefined,
      greenhouse_id: selectedGreenhouseId.value,
    })) as unknown as ZoneRecord
    zones.value = [...zones.value, created]
    newZoneName.value = ''
    newZoneDescription.value = ''
    zoneMode.value = 'select'
    emit('update:modelValue', created.id)
    showToast(`Зона «${created.name}» создана`, 'success')
  } catch (error) {
    showToast((error as Error).message || 'Ошибка создания зоны', 'error')
  } finally {
    creatingZone.value = false
  }
}
</script>
