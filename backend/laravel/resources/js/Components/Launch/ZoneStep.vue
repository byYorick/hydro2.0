<template>
    <section class="launch-step">
        <header class="launch-step__header">
            <h3 class="launch-step__title">Теплица и зона</h3>
            <p class="launch-step__desc">
                Выберите существующую теплицу и зону или создайте новые.
            </p>
        </header>

        <div class="launch-step__section">
            <h4 class="launch-step__subtitle">1. Теплица</h4>

            <div v-if="greenhouses.length > 0 && !showCreateGreenhouse" class="launch-step__grid">
                <button
                    v-for="gh in greenhouses"
                    :key="gh.id"
                    type="button"
                    class="launch-step__option"
                    :class="{ 'is-selected': selectedGreenhouseId === gh.id }"
                    @click="selectGreenhouse(gh.id)"
                >
                    <span class="launch-step__option-title">{{ gh.name }}</span>
                    <span v-if="gh.code" class="launch-step__option-meta">{{ gh.code }}</span>
                </button>
            </div>

            <div v-else-if="!showCreateGreenhouse" class="launch-step__empty">
                Нет созданных теплиц — создайте первую.
            </div>

            <button
                v-if="!showCreateGreenhouse"
                type="button"
                class="launch-step__add-btn"
                @click="showCreateGreenhouse = true"
            >
                + Создать теплицу
            </button>

            <div v-if="showCreateGreenhouse" class="launch-step__form">
                <label class="launch-field">
                    <span class="launch-field__label">Название</span>
                    <input
                        v-model="newGreenhouseName"
                        type="text"
                        class="launch-field__control"
                        placeholder="Напр.: Теплица #1"
                        maxlength="120"
                    />
                </label>
                <label class="launch-field">
                    <span class="launch-field__label">UID</span>
                    <input
                        v-model="newGreenhouseUid"
                        type="text"
                        class="launch-field__control"
                        placeholder="gh-1"
                        maxlength="64"
                    />
                </label>
                <label class="launch-field">
                    <span class="launch-field__label">Тип</span>
                    <select v-model="newGreenhouseType" class="launch-field__control">
                        <option value="">Не указан</option>
                        <option v-for="type in greenhouseTypes" :key="type.id" :value="type.code">
                            {{ type.name }}
                        </option>
                    </select>
                </label>
                <div class="launch-step__form-actions">
                    <button
                        type="button"
                        class="launch-step__btn launch-step__btn--primary"
                        :disabled="!newGreenhouseName.trim() || creatingGreenhouse"
                        @click="createGreenhouse"
                    >
                        {{ creatingGreenhouse ? 'Создание…' : 'Создать' }}
                    </button>
                    <button
                        type="button"
                        class="launch-step__btn launch-step__btn--ghost"
                        @click="showCreateGreenhouse = false"
                    >
                        Отмена
                    </button>
                </div>
            </div>
        </div>

        <div v-if="selectedGreenhouseId" class="launch-step__section">
            <h4 class="launch-step__subtitle">2. Зона</h4>

            <div v-if="filteredZones.length > 0 && !showCreateZone" class="launch-step__grid">
                <button
                    v-for="zone in filteredZones"
                    :key="zone.id"
                    type="button"
                    class="launch-step__option"
                    :class="{ 'is-selected': modelValue === zone.id }"
                    @click="selectZone(zone.id)"
                >
                    <span class="launch-step__option-title">{{ zone.name }}</span>
                    <span v-if="zone.status" class="launch-step__option-meta">
                        {{ zone.status }}
                    </span>
                </button>
            </div>

            <div v-else-if="!showCreateZone" class="launch-step__empty">
                В выбранной теплице нет зон — создайте первую.
            </div>

            <button
                v-if="!showCreateZone"
                type="button"
                class="launch-step__add-btn"
                @click="showCreateZone = true"
            >
                + Создать зону
            </button>

            <div v-if="showCreateZone" class="launch-step__form">
                <label class="launch-field">
                    <span class="launch-field__label">Название</span>
                    <input
                        v-model="newZoneName"
                        type="text"
                        class="launch-field__control"
                        placeholder="Напр.: Zone A"
                        maxlength="120"
                    />
                </label>
                <label class="launch-field">
                    <span class="launch-field__label">Описание (опционально)</span>
                    <input
                        v-model="newZoneDescription"
                        type="text"
                        class="launch-field__control"
                        maxlength="255"
                    />
                </label>
                <div class="launch-step__form-actions">
                    <button
                        type="button"
                        class="launch-step__btn launch-step__btn--primary"
                        :disabled="!newZoneName.trim() || creatingZone"
                        @click="createZone"
                    >
                        {{ creatingZone ? 'Создание…' : 'Создать' }}
                    </button>
                    <button
                        type="button"
                        class="launch-step__btn launch-step__btn--ghost"
                        @click="showCreateZone = false"
                    >
                        Отмена
                    </button>
                </div>
            </div>
        </div>
    </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { api } from '@/services/api';
import { useToast } from '@/composables/useToast';

interface GreenhouseRecord {
    id: number;
    name: string;
    code?: string;
    type?: string | null;
}
interface GreenhouseType {
    id: number;
    code: string;
    name: string;
}
interface ZoneRecord {
    id: number;
    name: string;
    status?: string | null;
    greenhouse_id?: number | null;
}

interface Props {
    modelValue?: number;
}

const props = withDefaults(defineProps<Props>(), { modelValue: undefined });

const emit = defineEmits<{
    (event: 'update:modelValue', value: number): void;
}>();

const { showToast } = useToast();

const greenhouses = ref<GreenhouseRecord[]>([]);
const greenhouseTypes = ref<GreenhouseType[]>([]);
const zones = ref<ZoneRecord[]>([]);

const selectedGreenhouseId = ref<number | null>(null);

const showCreateGreenhouse = ref(false);
const newGreenhouseName = ref('');
const newGreenhouseUid = ref('');
const newGreenhouseType = ref('');
const creatingGreenhouse = ref(false);

function slugify(text: string): string {
    const translit: Record<string, string> = {
        а: 'a', б: 'b', в: 'v', г: 'g', д: 'd', е: 'e', ё: 'e', ж: 'zh', з: 'z',
        и: 'i', й: 'y', к: 'k', л: 'l', м: 'm', н: 'n', о: 'o', п: 'p', р: 'r',
        с: 's', т: 't', у: 'u', ф: 'f', х: 'h', ц: 'c', ч: 'ch', ш: 'sh', щ: 'sch',
        ъ: '', ы: 'y', ь: '', э: 'e', ю: 'yu', я: 'ya',
    };
    return text
        .toLowerCase()
        .split('')
        .map((ch) => translit[ch] ?? ch)
        .join('')
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-+|-+$/g, '')
        .slice(0, 64);
}

const showCreateZone = ref(false);
const newZoneName = ref('');
const newZoneDescription = ref('');
const creatingZone = ref(false);

const filteredZones = computed(() =>
    zones.value.filter((z) => z.greenhouse_id === selectedGreenhouseId.value),
);

function toArray<T>(value: unknown): T[] {
    if (Array.isArray(value)) return value as T[];
    if (value && typeof value === 'object') {
        const obj = value as { data?: unknown };
        if (Array.isArray(obj.data)) return obj.data as T[];
    }
    return [];
}

async function loadAll() {
    try {
        const [ghList, types, zoneList] = await Promise.all([
            api.greenhouses.list(),
            api.greenhouses.types(),
            api.zones.list(),
        ]);
        greenhouses.value = toArray<GreenhouseRecord>(ghList);
        greenhouseTypes.value = toArray<GreenhouseType>(types);
        zones.value = toArray<ZoneRecord>(zoneList);

        if (props.modelValue) {
            const selectedZone = zones.value.find((z) => z.id === props.modelValue);
            if (selectedZone?.greenhouse_id) {
                selectedGreenhouseId.value = selectedZone.greenhouse_id;
            }
        } else if (greenhouses.value.length === 1) {
            selectedGreenhouseId.value = greenhouses.value[0].id;
        }
    } catch (error) {
        showToast((error as Error).message || 'Ошибка загрузки теплиц/зон', 'error');
    }
}

onMounted(loadAll);

watch(
    () => props.modelValue,
    (zoneId) => {
        if (!zoneId) return;
        const zone = zones.value.find((z) => z.id === zoneId);
        if (zone?.greenhouse_id) selectedGreenhouseId.value = zone.greenhouse_id;
    },
);

function selectGreenhouse(id: number) {
    selectedGreenhouseId.value = id;
    showCreateGreenhouse.value = false;
    if (props.modelValue) {
        const currentZone = zones.value.find((z) => z.id === props.modelValue);
        if (currentZone?.greenhouse_id !== id) {
            emit('update:modelValue', 0);
        }
    }
}

function selectZone(id: number) {
    emit('update:modelValue', id);
}

async function createGreenhouse() {
    const name = newGreenhouseName.value.trim();
    if (!name) return;
    const uid = (newGreenhouseUid.value.trim() || slugify(name)) || `gh-${Date.now()}`;
    creatingGreenhouse.value = true;
    try {
        const created = await api.greenhouses.create({
            uid,
            name,
            type: newGreenhouseType.value || null,
        });
        const record = created as unknown as GreenhouseRecord;
        greenhouses.value = [...greenhouses.value, record];
        selectedGreenhouseId.value = record.id;
        showCreateGreenhouse.value = false;
        newGreenhouseName.value = '';
        newGreenhouseUid.value = '';
        newGreenhouseType.value = '';
        showToast(`Теплица «${record.name}» создана`, 'success');
    } catch (error) {
        showToast((error as Error).message || 'Ошибка создания теплицы', 'error');
    } finally {
        creatingGreenhouse.value = false;
    }
}

async function createZone() {
    if (!selectedGreenhouseId.value) return;
    const name = newZoneName.value.trim();
    if (!name) return;
    creatingZone.value = true;
    try {
        const created = await api.zones.create({
            name,
            description: newZoneDescription.value.trim() || undefined,
            greenhouse_id: selectedGreenhouseId.value,
        });
        const record = created as unknown as ZoneRecord;
        zones.value = [...zones.value, record];
        showCreateZone.value = false;
        newZoneName.value = '';
        newZoneDescription.value = '';
        emit('update:modelValue', record.id);
        showToast(`Зона «${record.name}» создана`, 'success');
    } catch (error) {
        showToast((error as Error).message || 'Ошибка создания зоны', 'error');
    } finally {
        creatingZone.value = false;
    }
}
</script>

<style scoped>
.launch-step {
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
}

.launch-step__title {
    font-size: 1rem;
    font-weight: 600;
    margin: 0 0 0.25rem;
}

.launch-step__desc {
    margin: 0;
    opacity: 0.75;
    font-size: 0.875rem;
}

.launch-step__section {
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
}

.launch-step__subtitle {
    font-size: 0.8rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    opacity: 0.8;
    margin: 0;
}

.launch-step__grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 0.5rem;
}

.launch-step__option {
    background: rgba(148, 163, 184, 0.06);
    border: 1px solid rgba(148, 163, 184, 0.25);
    border-radius: 0.5rem;
    padding: 0.75rem;
    color: inherit;
    cursor: pointer;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    text-align: left;
}

.is-selected.launch-step__option,
.launch-step__option.is-selected {
    border-color: rgba(56, 189, 248, 0.7);
    background: rgba(56, 189, 248, 0.1);
}

.launch-step__option-title {
    font-weight: 600;
}

.launch-step__option-meta {
    font-size: 0.75rem;
    opacity: 0.65;
}

.launch-step__empty {
    padding: 0.75rem;
    background: rgba(251, 191, 36, 0.08);
    border: 1px solid rgba(251, 191, 36, 0.35);
    border-radius: 0.5rem;
    font-size: 0.85rem;
}

.launch-step__add-btn {
    align-self: flex-start;
    padding: 0.4rem 0.8rem;
    background: transparent;
    border: 1px dashed rgba(148, 163, 184, 0.45);
    border-radius: 0.375rem;
    color: inherit;
    cursor: pointer;
    font-size: 0.85rem;
}

.launch-step__add-btn:hover {
    background: rgba(148, 163, 184, 0.08);
}

.launch-step__form {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    padding: 0.75rem;
    border: 1px solid rgba(148, 163, 184, 0.25);
    border-radius: 0.5rem;
    background: rgba(148, 163, 184, 0.04);
}

.launch-step__form-actions {
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
}

.launch-step__btn {
    padding: 0.4rem 0.8rem;
    border-radius: 0.375rem;
    border: 1px solid transparent;
    cursor: pointer;
    font-weight: 500;
    font-size: 0.85rem;
}

.launch-step__btn:disabled {
    cursor: not-allowed;
    opacity: 0.55;
}

.launch-step__btn--primary {
    background: rgb(56, 189, 248);
    color: #0f172a;
}

.launch-step__btn--ghost {
    background: transparent;
    color: inherit;
}

.launch-field {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
}

.launch-field__label {
    font-size: 0.72rem;
    opacity: 0.75;
    text-transform: uppercase;
}

.launch-field__control {
    padding: 0.45rem 0.6rem;
    border-radius: 0.375rem;
    border: 1px solid rgba(148, 163, 184, 0.35);
    background: rgba(15, 23, 42, 0.35);
    color: inherit;
    font-size: 0.875rem;
}
</style>
