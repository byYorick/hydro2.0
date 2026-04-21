import { computed, type ComputedRef } from 'vue';
import type { AutomationProfile } from '@/schemas/automationProfile';

export type AutomationContractStatus = 'passed' | 'active' | 'blocker' | 'optional';

export type AutomationContractSubsystem =
    | 'bindings'
    | 'contour'
    | 'irrigation'
    | 'correction'
    | 'lighting'
    | 'climate';

export interface AutomationContract {
    id: string;
    subsystem: AutomationContractSubsystem;
    component: string;
    title: string;
    description?: string;
    status: AutomationContractStatus;
    required: boolean;
    action?: { label: string; target: string };
}

interface Inputs {
    profile: ComputedRef<AutomationProfile>;
    systemTypeLocked: ComputedRef<boolean>;
}

function isFilled(v: unknown): boolean {
    return v !== null && v !== undefined && v !== '';
}

export function useAutomationContracts(inputs: Inputs) {
    const contracts = computed<AutomationContract[]>(() => {
        const p = inputs.profile.value;
        const a = p.assignments;
        const water = p.waterForm;
        const lighting = p.lightingForm;
        const climate = p.zoneClimateForm;

        const out: AutomationContract[] = [];

        // ── Bindings (обязательные) ─────────────────────────────
        out.push({
            id: 'bindings.irrigation',
            subsystem: 'bindings',
            component: 'irrigation',
            title: 'Привязка · irrigation',
            description: 'Узел полива (pump_main + valve_irrigation).',
            status: a.irrigation ? 'passed' : 'blocker',
            required: true,
            action: { label: 'К привязкам', target: 'bindings' },
        });
        out.push({
            id: 'bindings.ph_correction',
            subsystem: 'bindings',
            component: 'ph_correction',
            title: 'Привязка · pH correction',
            description: 'Узел коррекции pH (pump_acid + pump_base).',
            status: a.ph_correction ? 'passed' : 'blocker',
            required: true,
            action: { label: 'К привязкам', target: 'bindings' },
        });
        out.push({
            id: 'bindings.ec_correction',
            subsystem: 'bindings',
            component: 'ec_correction',
            title: 'Привязка · EC correction',
            description: 'Узел коррекции EC (pump_a..d).',
            status: a.ec_correction ? 'passed' : 'blocker',
            required: true,
            action: { label: 'К привязкам', target: 'bindings' },
        });

        // ── Contour (водный контур) ─────────────────────────────
        const tanksOk =
            isFilled(water.cleanTankFillL) &&
            water.cleanTankFillL > 0 &&
            isFilled(water.nutrientTankTargetL) &&
            water.nutrientTankTargetL > 0;

        out.push({
            id: 'contour.topology',
            subsystem: 'contour',
            component: 'topology',
            title: 'Водный контур · топология',
            description: inputs.systemTypeLocked.value
                ? `${water.systemType} из рецепта · ${water.tanksCount} бака`
                : 'Топология не задана рецептом.',
            status: inputs.systemTypeLocked.value ? 'passed' : 'blocker',
            required: true,
            action: { label: 'К контуру', target: 'contour' },
        });

        out.push({
            id: 'contour.tanks',
            subsystem: 'contour',
            component: 'tanks',
            title: 'Водный контур · баки и насосы',
            description: 'Объёмы баков и производительность насосов.',
            status: tanksOk ? 'passed' : 'blocker',
            required: true,
            action: { label: 'К контуру', target: 'contour' },
        });

        // ── Irrigation ──────────────────────────────────────────
        const irrigationOk =
            water.intervalMinutes > 0 && water.durationSeconds > 0;
        out.push({
            id: 'irrigation.schedule',
            subsystem: 'irrigation',
            component: 'schedule',
            title: 'Полив · расписание',
            description: 'Интервал и длительность полива.',
            status: irrigationOk ? 'passed' : 'blocker',
            required: true,
            action: { label: 'К поливу', target: 'irrigation' },
        });

        const smart = water.irrigationDecisionStrategy === 'smart_soil_v1';
        if (smart) {
            out.push({
                id: 'irrigation.soil_moisture',
                subsystem: 'irrigation',
                component: 'soil_moisture',
                title: 'Полив · датчик влажности',
                description: 'SMART mode требует привязки soil_moisture_sensor.',
                status: a.soil_moisture_sensor ? 'passed' : 'blocker',
                required: true,
                action: { label: 'К поливу', target: 'irrigation' },
            });
        }

        // ── Correction (pH/EC targets) ──────────────────────────
        const correctionOk =
            water.targetPh > 0 && water.targetEc > 0;
        out.push({
            id: 'correction.targets',
            subsystem: 'correction',
            component: 'targets',
            title: 'Коррекция · targets',
            description: 'Target pH и EC из рецепта либо override.',
            status: correctionOk ? 'passed' : 'blocker',
            required: true,
            action: { label: 'К коррекции', target: 'correction' },
        });

        // ── Lighting (optional) ─────────────────────────────────
        if (lighting.enabled) {
            out.push({
                id: 'lighting.binding',
                subsystem: 'lighting',
                component: 'binding',
                title: 'Свет · привязка канала',
                description: 'Для включённого света нужен light channel.',
                status: a.light ? 'passed' : 'blocker',
                required: true,
                action: { label: 'К свету', target: 'lighting' },
            });
            out.push({
                id: 'lighting.schedule',
                subsystem: 'lighting',
                component: 'schedule',
                title: 'Свет · расписание',
                description: 'Lux day/night, hours on, schedule.',
                status:
                    lighting.hoursOn > 0 && lighting.luxDay >= 0 ? 'passed' : 'blocker',
                required: true,
                action: { label: 'К свету', target: 'lighting' },
            });
        } else {
            out.push({
                id: 'lighting.enabled',
                subsystem: 'lighting',
                component: 'enabled',
                title: 'Свет',
                description: 'Досветка выключена — пропускается.',
                status: 'optional',
                required: false,
                action: { label: 'К свету', target: 'lighting' },
            });
        }

        // ── Climate (optional) ──────────────────────────────────
        if (climate.enabled) {
            const hasClimateBinding =
                a.co2_sensor || a.co2_actuator || a.root_vent_actuator;
            out.push({
                id: 'climate.binding',
                subsystem: 'climate',
                component: 'binding',
                title: 'Климат · привязки',
                description: 'Хотя бы один из: co2_sensor / co2_actuator / root_vent.',
                status: hasClimateBinding ? 'passed' : 'blocker',
                required: true,
                action: { label: 'К климату', target: 'climate' },
            });
        } else {
            out.push({
                id: 'climate.enabled',
                subsystem: 'climate',
                component: 'enabled',
                title: 'Климат',
                description: 'Zone climate выключен — пропускается.',
                status: 'optional',
                required: false,
                action: { label: 'К климату', target: 'climate' },
            });
        }

        return out;
    });

    const requiredContracts = computed(() => contracts.value.filter((c) => c.required));
    const blockers = computed(() => contracts.value.filter((c) => c.status === 'blocker'));
    const summary = computed(() => {
        const req = requiredContracts.value;
        const passed = req.filter((c) => c.status === 'passed').length;
        return { passed, total: req.length, blockers: blockers.value.length };
    });

    return { contracts, requiredContracts, blockers, summary };
}
