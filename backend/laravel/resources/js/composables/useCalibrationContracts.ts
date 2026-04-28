import { computed, type ComputedRef } from 'vue';
import type { PumpCalibration } from '@/types/PidConfig';
import type { Device } from '@/types';
import type { LaunchFlowReadinessBlocker } from '@/services/api/launchFlow';

export type ContractStatus = 'passed' | 'active' | 'blocker' | 'optional';

export type ContractSubsystem = 'sensor' | 'pump' | 'process' | 'correction' | 'pid';

export interface CalibrationContract {
    id: string;
    subsystem: ContractSubsystem;
    component: string;
    title: string;
    description?: string;
    status: ContractStatus;
    required: boolean;
    action?: { label: string; target: string };
}

export interface ContractInputs {
    pumps: ComputedRef<PumpCalibration[]>;
    devices: ComputedRef<Device[]>;
    processDocs: ComputedRef<Record<string, unknown>>;
    correctionDoc: ComputedRef<Record<string, unknown> | null>;
    pidDoc: ComputedRef<Record<string, unknown> | null>;
    readinessBlockers: ComputedRef<LaunchFlowReadinessBlocker[]>;
}

const REQUIRED_PUMPS: Array<{ role: string; title: string; component: string }> = [
    { role: 'pump_acid', title: 'Pump · pH-', component: 'ph_down' },
    { role: 'pump_base', title: 'Pump · pH+', component: 'ph_up' },
    { role: 'pump_a', title: 'Pump · NPK', component: 'npk' },
];

const REQUIRED_PROCESS_MODES = ['generic', 'solution_fill'];

function pumpCalibrated(pumps: PumpCalibration[], role: string): boolean {
    const p = pumps.find((x) => x.role === role);
    return !!p?.ml_per_sec && p.ml_per_sec > 0;
}

function pumpHasBinding(pumps: PumpCalibration[], role: string): boolean {
    const p = pumps.find((x) => x.role === role);
    return p != null && p.node_channel_id > 0;
}

function hasSensor(devices: Device[], metric: 'PH' | 'EC'): boolean {
    return devices.some((d) =>
        (d as { channels?: Array<{ metric?: string }> }).channels?.some((c) => c.metric === metric),
    );
}

export function useCalibrationContracts(inputs: ContractInputs) {
    function mapReadinessBlockerToContract(blocker: LaunchFlowReadinessBlocker, index: number): CalibrationContract {
        const codePrefix = blocker.code.split(':')[0] || 'readiness';
        const role = blocker.action?.role ?? '';
        const pidType = blocker.action?.pid_type ?? '';

        if (codePrefix === 'missing_binding') {
            return {
                id: `readiness.binding.${index}`,
                subsystem: 'pump',
                component: role || 'binding',
                title: blocker.message,
                description: 'Глобальный readiness-блокер launch-flow.',
                status: 'blocker',
                required: true,
                action: { label: blocker.action?.label ?? 'К насосам', target: 'pumps' },
            };
        }

        if (codePrefix === 'missing_pid_config') {
            return {
                id: `readiness.pid.${index}`,
                subsystem: 'pid',
                component: pidType || 'pid',
                title: blocker.message,
                description: 'Глобальный readiness-блокер launch-flow.',
                status: 'blocker',
                required: true,
                action: { label: blocker.action?.label ?? 'К PID', target: 'pid' },
            };
        }

        if (codePrefix === 'missing_process_calibration') {
            return {
                id: `readiness.process.${index}`,
                subsystem: 'process',
                component: blocker.action?.mode || 'process',
                title: blocker.message,
                description: 'Глобальный readiness-блокер launch-flow.',
                status: 'blocker',
                required: true,
                action: { label: blocker.action?.label ?? 'К процессу', target: 'process' },
            };
        }

        return {
            id: `readiness.generic.${index}`,
            subsystem: 'process',
            component: blocker.code,
            title: blocker.message,
            description: 'Глобальный readiness-блокер launch-flow.',
            status: 'blocker',
            required: true,
        };
    }

    const contracts = computed<CalibrationContract[]>(() => {
        const pumps = inputs.pumps.value;
        const devices = inputs.devices.value;
        const processDocs = inputs.processDocs.value;
        const correctionDoc = inputs.correctionDoc.value;
        const pidDoc = inputs.pidDoc.value;

        const out: CalibrationContract[] = [];

        // 1. Sensor contract
        const hasPh = hasSensor(devices, 'PH');
        const hasEc = hasSensor(devices, 'EC');
        out.push({
            id: 'sensor.ph_ec',
            subsystem: 'sensor',
            component: 'pH/EC',
            title: 'Sensor · pH/EC',
            description: 'pH и EC сенсоры привязаны и готовы к измерениям.',
            status: hasPh && hasEc ? 'passed' : 'blocker',
            required: true,
            action: { label: 'К сенсорам', target: 'sensors' },
        });

        // 2. Required pump contracts
        for (const desc of REQUIRED_PUMPS) {
            const calibrated = pumpCalibrated(pumps, desc.role);
            const bound = pumpHasBinding(pumps, desc.role);
            const status: ContractStatus = calibrated
                ? 'passed'
                : bound
                  ? 'blocker'
                  : 'blocker';
            out.push({
                id: `pump.${desc.component}`,
                subsystem: 'pump',
                component: desc.component,
                title: desc.title,
                description: bound
                    ? 'Канал привязан, нужна калибровка ml/sec.'
                    : 'Канал не привязан — сначала привяжите ноду.',
                status,
                required: true,
                action: { label: 'К насосам', target: 'pumps' },
            });
        }

        // 3. Process contract
        const savedModes = REQUIRED_PROCESS_MODES.filter((m) => processDocs[m] != null);
        out.push({
            id: 'process.solution_fill',
            subsystem: 'process',
            component: 'solution_fill',
            title: 'Process · solution_fill',
            description: 'Настройки observe/gain для фаз solution_fill и generic.',
            status: savedModes.length === REQUIRED_PROCESS_MODES.length ? 'passed' : 'blocker',
            required: true,
            action: { label: 'К процессу', target: 'process' },
        });

        // 4. Correction contract (optional)
        out.push({
            id: 'correction.config',
            subsystem: 'correction',
            component: 'config',
            title: 'Correction · config',
            description: 'Authority-документ correction config применён для зоны.',
            status:
                correctionDoc && Object.keys(correctionDoc).length > 0
                    ? 'passed'
                    : 'optional',
            required: false,
            action: { label: 'К correction', target: 'correction' },
        });

        // 5. PID contract (optional)
        out.push({
            id: 'pid.zone_override',
            subsystem: 'pid',
            component: 'override',
            title: 'PID · override',
            description: 'Zone PID override или autotune применены.',
            status: pidDoc && Object.keys(pidDoc).length > 0 ? 'passed' : 'optional',
            required: false,
            action: { label: 'К PID', target: 'pid' },
        });

        const globalReadinessBlockers = inputs.readinessBlockers.value.map(mapReadinessBlockerToContract);

        return [...out, ...globalReadinessBlockers];
    });

    const requiredContracts = computed(() => contracts.value.filter((c) => c.required));
    const blockers = computed(() => contracts.value.filter((c) => c.status === 'blocker'));
    const optional = computed(() => contracts.value.filter((c) => !c.required));

    const summary = computed(() => {
        const req = requiredContracts.value;
        const passed = req.filter((c) => c.status === 'passed').length;
        return {
            passed,
            total: req.length,
            blockers: blockers.value.length,
        };
    });

    const overallStatus = computed<ContractStatus>(() => {
        if (summary.value.blockers > 0) return 'blocker';
        if (summary.value.passed === summary.value.total) return 'passed';
        return 'active';
    });

    return {
        contracts,
        requiredContracts,
        blockers,
        optional,
        summary,
        overallStatus,
    };
}
