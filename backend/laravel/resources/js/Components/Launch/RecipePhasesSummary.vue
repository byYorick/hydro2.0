<template>
    <div v-if="phases.length" class="phases-summary">
        <div class="phases-summary__header">
            <span>📖</span>
            <span class="phases-summary__title">Сводка фаз рецепта</span>
            <span class="phases-summary__count">{{ phases.length }}</span>
        </div>

        <div class="phases-summary__scroll">
            <table class="phases-summary__table">
                <thead>
                    <tr>
                        <th>Фаза</th>
                        <th>Длит.</th>
                        <th>pH</th>
                        <th>EC (mS/cm)</th>
                        <th>T °C</th>
                        <th>Вл. %</th>
                        <th>Свет</th>
                        <th>Полив</th>
                    </tr>
                </thead>
                <tbody>
                    <tr v-for="(phase, index) in rows" :key="index">
                        <td>
                            <span class="phases-summary__name">{{ phase.name || `Фаза ${index + 1}` }}</span>
                        </td>
                        <td>{{ phase.duration }}</td>
                        <td>
                            <div>{{ phase.phTarget }}</div>
                            <div class="phases-summary__range">{{ phase.phRange }}</div>
                        </td>
                        <td>
                            <div>{{ phase.ecTarget }}</div>
                            <div class="phases-summary__range">{{ phase.ecRange }}</div>
                        </td>
                        <td>
                            <div v-if="phase.dayNight.temp">
                                <span class="phases-summary__dn">день {{ phase.dayNight.temp.day }}</span>
                                <span class="phases-summary__dn phases-summary__dn--night">ночь {{ phase.dayNight.temp.night }}</span>
                            </div>
                            <div v-else>{{ phase.tempFlat }}</div>
                        </td>
                        <td>
                            <div v-if="phase.dayNight.humidity">
                                <span class="phases-summary__dn">день {{ phase.dayNight.humidity.day }}</span>
                                <span class="phases-summary__dn phases-summary__dn--night">ночь {{ phase.dayNight.humidity.night }}</span>
                            </div>
                            <div v-else>{{ phase.humidityFlat }}</div>
                        </td>
                        <td>
                            <div>{{ phase.lighting }}</div>
                            <div v-if="phase.lightStart" class="phases-summary__range">с {{ phase.lightStart }}</div>
                        </td>
                        <td>
                            <div>{{ phase.irrigation }}</div>
                            <div v-if="phase.irrigationMode" class="phases-summary__range">{{ phase.irrigationMode }}</div>
                        </td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';

interface RawPhase {
    name?: string | null;
    duration_hours?: number | null;
    duration_days?: number | null;
    ph_target?: number | null;
    ph_min?: number | null;
    ph_max?: number | null;
    ec_target?: number | null;
    ec_min?: number | null;
    ec_max?: number | null;
    temp_air_target?: number | null;
    humidity_target?: number | null;
    lighting_photoperiod_hours?: number | null;
    lighting_start_time?: string | null;
    irrigation_interval_sec?: number | null;
    irrigation_duration_sec?: number | null;
    irrigation_mode?: string | null;
    extensions?: Record<string, unknown> | null;
}

interface Props {
    phases: RawPhase[];
}

const props = withDefaults(defineProps<Props>(), { phases: () => [] });

function num(value: unknown): number | null {
    if (typeof value === 'number' && Number.isFinite(value)) return value;
    if (typeof value === 'string' && value.trim() !== '') {
        const parsed = Number(value);
        if (Number.isFinite(parsed)) return parsed;
    }
    return null;
}

function fmt(value: number | null, digits = 1): string {
    if (value === null) return '—';
    const rounded = Math.round(value * Math.pow(10, digits)) / Math.pow(10, digits);
    return rounded.toFixed(digits).replace(/\.0+$/, '');
}

function fmtInt(value: number | null): string {
    if (value === null) return '—';
    return String(Math.round(value));
}

function getDayNight(
    ext: Record<string, unknown> | null | undefined,
    key: 'temperature' | 'humidity',
): { day: string; night: string } | null {
    if (!ext || typeof ext !== 'object') return null;
    const dn = (ext as { day_night?: Record<string, unknown> })?.day_night;
    if (!dn || typeof dn !== 'object') return null;
    const block = (dn as Record<string, unknown>)[key];
    if (!block || typeof block !== 'object') return null;
    const b = block as { day?: unknown; night?: unknown };
    const day = num(b.day);
    const night = num(b.night);
    if (day === null && night === null) return null;
    return {
        day: key === 'humidity' ? fmtInt(day) : fmt(day, 1),
        night: key === 'humidity' ? fmtInt(night) : fmt(night, 1),
    };
}

function durationLabel(phase: RawPhase): string {
    const hours = num(phase.duration_hours);
    const days = num(phase.duration_days);
    if (days !== null && days >= 1) {
        return `${fmt(days, 1)} д.`;
    }
    if (hours !== null && hours > 0) {
        return `${fmt(hours, 0)} ч`;
    }
    return '—';
}

function lightingLabel(phase: RawPhase): string {
    const hrs = num(phase.lighting_photoperiod_hours);
    if (hrs === null) return '—';
    return `${fmtInt(hrs)} ч`;
}

function irrigationLabel(phase: RawPhase): string {
    const interval = num(phase.irrigation_interval_sec);
    const duration = num(phase.irrigation_duration_sec);
    if (interval === null && duration === null) return '—';
    const parts: string[] = [];
    if (interval !== null) parts.push(`каждые ${Math.round(interval / 60)} мин`);
    if (duration !== null) parts.push(`×${duration} с`);
    return parts.join(' ');
}

const rows = computed(() =>
    props.phases.map((phase) => ({
        name: phase.name || '',
        duration: durationLabel(phase),
        phTarget: fmt(num(phase.ph_target), 1),
        phRange: `${fmt(num(phase.ph_min), 1)} – ${fmt(num(phase.ph_max), 1)}`,
        ecTarget: fmt(num(phase.ec_target), 1),
        ecRange: `${fmt(num(phase.ec_min), 1)} – ${fmt(num(phase.ec_max), 1)}`,
        tempFlat: fmt(num(phase.temp_air_target), 1),
        humidityFlat: fmtInt(num(phase.humidity_target)),
        dayNight: {
            temp: getDayNight(phase.extensions as Record<string, unknown> | null, 'temperature'),
            humidity: getDayNight(phase.extensions as Record<string, unknown> | null, 'humidity'),
        },
        lighting: lightingLabel(phase),
        lightStart: phase.lighting_start_time || '',
        irrigation: irrigationLabel(phase),
        irrigationMode: phase.irrigation_mode || '',
    })),
);
</script>

<style scoped>
.phases-summary {
    border: 1px solid rgba(148, 163, 184, 0.25);
    border-radius: 0.5rem;
    background: rgba(148, 163, 184, 0.04);
    padding: 0.5rem 0.75rem;
}

.phases-summary__header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.4rem;
    font-size: 0.75rem;
}

.phases-summary__title {
    font-weight: 600;
    color: var(--text-primary, inherit);
}

.phases-summary__count {
    margin-left: auto;
    padding: 0 0.4rem;
    border-radius: 9999px;
    background: rgba(56, 189, 248, 0.12);
    color: rgb(56, 189, 248);
    font-size: 0.7rem;
    font-weight: 600;
}

.phases-summary__scroll {
    overflow-x: auto;
}

.phases-summary__table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.72rem;
}

.phases-summary__table th {
    text-align: left;
    padding: 0.25rem 0.5rem;
    font-weight: 600;
    letter-spacing: 0.02em;
    text-transform: uppercase;
    font-size: 0.65rem;
    color: rgba(148, 163, 184, 0.85);
    border-bottom: 1px solid rgba(148, 163, 184, 0.2);
    white-space: nowrap;
}

.phases-summary__table td {
    padding: 0.35rem 0.5rem;
    border-bottom: 1px solid rgba(148, 163, 184, 0.1);
    vertical-align: top;
    color: var(--text-primary, inherit);
}

.phases-summary__table tbody tr:hover td {
    background: rgba(148, 163, 184, 0.06);
}

.phases-summary__name {
    font-weight: 600;
    white-space: nowrap;
}

.phases-summary__range {
    font-size: 0.65rem;
    opacity: 0.6;
    margin-top: 0.1rem;
}

.phases-summary__dn {
    display: inline-block;
    padding: 0.05rem 0.35rem;
    border-radius: 0.25rem;
    font-size: 0.65rem;
    margin-right: 0.25rem;
    background: rgba(56, 189, 248, 0.1);
    color: rgb(125, 211, 252);
    white-space: nowrap;
}

.phases-summary__dn--night {
    background: rgba(148, 163, 184, 0.12);
    color: rgba(148, 163, 184, 0.9);
}
</style>
