<template>
    <div class="cal-hub">
        <CalibrationReadinessBar
            :contracts="contracts"
            :summary="summary"
            @open-blockers="blockersOpen = true"
            @open-pump-wizard="openPumpWizardFromReadiness"
            @open-contract="onContractClick"
        />

        <div class="cal-hub__grid">
            <aside class="cal-hub__sidebar">
                <div class="cal-hub__section">
                    <div class="cal-hub__section-label">Базовая калибровка</div>
                    <CalibrationSidebarItem
                        title="Сенсоры"
                        subtitle="pH · EC · история"
                        :state="navStates.sensors.state"
                        :count="navStates.sensors.count"
                        :active="currentSub === 'sensors'"
                        :index="1"
                        @click="currentSub = 'sensors'"
                    />
                    <CalibrationSidebarItem
                        title="Насосы"
                        subtitle="дозирование · пределы runtime"
                        :state="navStates.pumps.state"
                        :count="navStates.pumps.count"
                        :active="currentSub === 'pumps'"
                        :index="2"
                        @click="currentSub = 'pumps'"
                    />
                    <CalibrationSidebarItem
                        title="Процесс"
                        subtitle="окно · отклик · 4 фазы"
                        :state="navStates.process.state"
                        :count="navStates.process.count"
                        :active="currentSub === 'process'"
                        :index="3"
                        :waiting-label="navStates.process.waitingLabel"
                        @click="currentSub = 'process'"
                    />
                </div>

                <div class="cal-hub__section">
                    <div class="cal-hub__section-label">Тонкая настройка</div>
                    <CalibrationSidebarItem
                        title="Коррекция"
                        subtitle="authority · пресеты"
                        :state="navStates.correction.state"
                        count="опц."
                        :active="currentSub === 'correction'"
                        @click="currentSub = 'correction'"
                    />
                    <CalibrationSidebarItem
                        title="PID и автонастройка"
                        subtitle="доводка контура"
                        :state="navStates.pid.state"
                        count="опц."
                        :active="currentSub === 'pid'"
                        @click="currentSub = 'pid'"
                    />
                </div>
            </aside>

            <main class="cal-hub__main">
                <CalibrationPumpsSubpage
                    v-if="currentSub === 'pumps'"
                    :zone-id="zoneId"
                    :pumps="pumps"
                    @calibrate="onPumpCalibrateFromRow"
                    @open-pump-wizard="openPumpWizardGeneric"
                    @export-csv="onExportCsv"
                />

                <section v-else-if="currentSub === 'sensors'" class="cal-sub-basic">
                    <div class="cal-sub-basic__head">
                        <h3>Калибровка сенсоров</h3>
                        <div class="cal-sub-basic__desc">
                            Отдельный контур калибровки сенсоров pH/EC и её история.
                        </div>
                    </div>
                    <SensorCalibrationStatus
                        :zone-id="zoneId"
                        :settings="sensorCalibrationSettings"
                    />
                </section>

                <section v-else-if="currentSub === 'process'" class="cal-sub-basic">
                    <div class="cal-sub-basic__head">
                        <h3>Калибровка процесса</h3>
                        <div class="cal-sub-basic__desc">
                            Окно наблюдения и коэффициенты отклика для фаз: наполнение / рециркуляция / полив / запасной профиль.
                        </div>
                    </div>
                    <ProcessCalibrationPanel :zone-id="zoneId" @saved="$emit('updated')" />
                </section>

                <section v-else-if="currentSub === 'correction'" class="cal-sub-basic">
                    <div class="cal-sub-basic__head">
                        <h3>Конфигурация коррекции</h3>
                        <div class="cal-sub-basic__desc">
                            Authority-редактор коррекции: база / переопределения / жизненный цикл пресетов / сравнение.
                        </div>
                    </div>
                    <CorrectionConfigForm :zone-id="zoneId" @saved="$emit('updated')" />
                </section>

                <section v-else-if="currentSub === 'pid'" class="cal-sub-basic">
                    <div class="cal-sub-basic__head">
                        <h3>PID и автонастройка</h3>
                        <div class="cal-sub-basic__desc">
                            Доводка контура коррекции. Открывайте только после базовой калибровки.
                        </div>
                    </div>
                    <div class="cal-sub-basic__pid">
                        <PidConfigForm
                            :zone-id="zoneId"
                            :phase-targets="phaseTargets"
                            @saved="$emit('updated')"
                        />
                        <RelayAutotuneTrigger :zone-id="zoneId" />
                    </div>
                </section>
            </main>
        </div>

        <CalibrationBlockersDrawer
            :open="blockersOpen"
            :blockers="blockers"
            @close="blockersOpen = false"
            @navigate="onBlockerNavigate"
        />

        <PumpCalibrationDrawer
            :show="pumpDrawerOpen"
            :zone-id="zoneId"
            :devices="zoneDevices"
            :pumps="pumps"
            :loading-run="pumpActions.loadingRun.value"
            :loading-save="pumpActions.loadingSave.value"
            :run-success-seq="pumpActions.runSeq.value"
            :save-success-seq="pumpActions.saveSeq.value"
            :last-run-token="pumpActions.lastRunToken.value"
            :initial-component="forcedComponent"
            :initial-node-channel-id="forcedNodeChannelId"
            @close="pumpDrawerOpen = false"
            @start="onPumpStart"
            @save="onPumpSave"
        />
    </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import CalibrationReadinessBar from '@/Components/Launch/Calibration/CalibrationReadinessBar.vue';
import CalibrationSidebarItem, { type NavState } from '@/Components/Launch/Calibration/CalibrationSidebarItem.vue';
import CalibrationPumpsSubpage, { type PumpRow } from '@/Components/Launch/Calibration/CalibrationPumpsSubpage.vue';
import CalibrationBlockersDrawer from '@/Components/Launch/Calibration/CalibrationBlockersDrawer.vue';
import PumpCalibrationDrawer from '@/Components/Launch/Calibration/PumpCalibrationDrawer.vue';
import SensorCalibrationStatus from '@/Components/SensorCalibrationStatus.vue';
import ProcessCalibrationPanel from '@/Components/ProcessCalibrationPanel.vue';
import CorrectionConfigForm from '@/Components/CorrectionConfigForm.vue';
import PidConfigForm from '@/Components/PidConfigForm.vue';
import RelayAutotuneTrigger from '@/Components/RelayAutotuneTrigger.vue';
import {
    useCalibrationContracts,
    type CalibrationContract,
} from '@/composables/useCalibrationContracts';
import { useSensorCalibrationSettings } from '@/composables/useSensorCalibrationSettings';
import { usePumpCalibrationActions } from '@/composables/usePumpCalibrationActions';
import { useToast } from '@/composables/useToast';
import { api } from '@/services/api';
import type { Device } from '@/types';
import type { PumpCalibration } from '@/types/PidConfig';
import type { RecipePhasePidTargets } from '@/composables/recipePhasePidTargets';
import type {
    PumpCalibrationComponent,
    PumpCalibrationRunPayload,
    PumpCalibrationSavePayload,
} from '@/types/Calibration';

interface Props {
    zoneId: number;
    phaseTargets?: RecipePhasePidTargets | null;
}

const props = withDefaults(defineProps<Props>(), { phaseTargets: null });
const emit = defineEmits<{ (e: 'updated'): void }>();

const { showToast } = useToast();
const sensorCalibrationSettings = useSensorCalibrationSettings();

type SubKey = 'sensors' | 'pumps' | 'process' | 'correction' | 'pid';
const currentSub = ref<SubKey>('pumps');

const pumps = ref<PumpCalibration[]>([]);
const zoneDevices = ref<Device[]>([]);
const processDocs = ref<Record<string, unknown>>({});
const correctionDoc = ref<Record<string, unknown> | null>(null);
const pidDoc = ref<Record<string, unknown> | null>(null);

const pumpsRef = computed(() => pumps.value);
const devicesRef = computed(() => zoneDevices.value);
const processDocsRef = computed(() => processDocs.value);
const correctionDocRef = computed(() => correctionDoc.value);
const pidDocRef = computed(() => pidDoc.value);

const { contracts, summary, blockers } = useCalibrationContracts({
    pumps: pumpsRef,
    devices: devicesRef,
    processDocs: processDocsRef,
    correctionDoc: correctionDocRef,
    pidDoc: pidDocRef,
});

const blockersOpen = ref(false);
const pumpDrawerOpen = ref(false);
const forcedComponent = ref<PumpCalibrationComponent | null>(null);
const forcedNodeChannelId = ref<number | null>(null);

const pumpActions = usePumpCalibrationActions({
    getZoneId: () => props.zoneId,
    showToast,
    onSaveSuccess: async () => {
        await loadPumpCalibrations();
        emit('updated');
    },
    onRunSuccess: async () => {
        await loadPumpCalibrations();
    },
});

// ── Nav states derived from contracts ────────────────────────────
const navStates = computed(() => {
    const pumpContracts = contracts.value.filter((c) => c.subsystem === 'pump');
    const pumpDone = pumpContracts.filter((c) => c.status === 'passed').length;
    const sensorContract = contracts.value.find((c) => c.subsystem === 'sensor');
    const processContract = contracts.value.find((c) => c.subsystem === 'process');
    const correctionContract = contracts.value.find((c) => c.subsystem === 'correction');
    const pidContract = contracts.value.find((c) => c.subsystem === 'pid');

    const pumpsBlocked = pumpContracts.some((c) => c.status === 'blocker');

    const state = (contract?: CalibrationContract): NavState => {
        if (!contract) return 'optional';
        if (contract.status === 'passed') return 'passed';
        if (contract.status === 'blocker') return 'blocker';
        if (contract.status === 'optional') return 'optional';
        return 'active';
    };

    return {
        sensors: {
            state: state(sensorContract),
            count: sensorContract?.status === 'passed' ? '2/2' : '0/2',
        },
        pumps: {
            state: pumpDone === pumpContracts.length ? ('passed' as NavState) : pumpsBlocked ? ('blocker' as NavState) : ('active' as NavState),
            count: `${pumpDone}/${pumpContracts.length}`,
        },
        process: {
            state: pumpsBlocked ? ('waiting' as NavState) : state(processContract),
            count: processContract?.status === 'passed' ? '4/4' : '0/4',
            waitingLabel: pumpsBlocked ? 'ждёт насосы' : '',
        },
        correction: { state: state(correctionContract), count: 'опц.' },
        pid: { state: state(pidContract), count: 'опц.' },
    };
});

// ── Data loaders ─────────────────────────────────────────────────
async function loadPumpCalibrations() {
    try {
        const resp = await api.zones.getPumpCalibrations<{
            pumps?: PumpCalibration[];
        } | PumpCalibration[]>(props.zoneId);
        let list: PumpCalibration[] = [];
        if (Array.isArray(resp)) list = resp as PumpCalibration[];
        else if (Array.isArray((resp as { pumps?: PumpCalibration[] })?.pumps))
            list = (resp as { pumps: PumpCalibration[] }).pumps;
        pumps.value = list;
    } catch {
        pumps.value = [];
    }
}

async function loadZoneDevices() {
    try {
        const resp = await api.nodes.list({
            zone_id: props.zoneId,
            include_unassigned: true,
            per_page: 100,
        });
        const list = Array.isArray(resp)
            ? resp
            : Array.isArray((resp as { data?: unknown[] })?.data)
              ? ((resp as { data: unknown[] }).data as unknown[])
              : [];
        zoneDevices.value = list as Device[];
    } catch {
        zoneDevices.value = [];
    }
}

async function loadProcessDocs() {
    const modes = ['generic', 'solution_fill', 'tank_recirc', 'irrigation'];
    const out: Record<string, unknown> = {};
    for (const mode of modes) {
        try {
            const doc = await api.automationConfigs.get(
                'zone',
                props.zoneId,
                `zone.process_calibration.${mode}`,
            );
            out[mode] = (doc as { payload?: unknown })?.payload ?? null;
        } catch {
            out[mode] = null;
        }
    }
    processDocs.value = out;
}

async function loadCorrectionDoc() {
    try {
        const doc = await api.automationConfigs.get('zone', props.zoneId, 'zone.correction');
        correctionDoc.value =
            (doc as { payload?: Record<string, unknown> })?.payload ?? null;
    } catch {
        correctionDoc.value = null;
    }
}

async function loadPidDoc() {
    try {
        const doc = await api.automationConfigs.get('zone', props.zoneId, 'zone.pid.ph');
        pidDoc.value = (doc as { payload?: Record<string, unknown> })?.payload ?? null;
    } catch {
        pidDoc.value = null;
    }
}

async function reloadAll() {
    await Promise.all([
        loadPumpCalibrations(),
        loadZoneDevices(),
        loadProcessDocs(),
        loadCorrectionDoc(),
        loadPidDoc(),
    ]);
}

onMounted(reloadAll);
watch(() => props.zoneId, reloadAll);

// ── Actions ───────────────────────────────────────────────────────
function onPumpCalibrateFromRow(pump: PumpRow) {
    if (!pump.canCalibrate) {
        showToast('Канал не привязан — привяжите на шаге «Автоматика»', 'warning');
        return;
    }
    forcedComponent.value = pump.component as PumpCalibrationComponent;
    forcedNodeChannelId.value = pump.nodeChannelId;
    pumpDrawerOpen.value = true;
}

function openPumpWizardGeneric() {
    currentSub.value = 'pumps';
    forcedComponent.value = null;
    forcedNodeChannelId.value = null;
    pumpDrawerOpen.value = true;
}

function openPumpWizardFromReadiness() {
    currentSub.value = 'pumps';
    const firstPending = contracts.value.find(
        (c) => c.subsystem === 'pump' && c.status === 'blocker',
    );
    if (firstPending) {
        const componentMap: Record<string, PumpCalibrationComponent> = {
            npk: 'npk',
            ph_down: 'ph_down',
            ph_up: 'ph_up',
        };
        forcedComponent.value = componentMap[firstPending.component] ?? null;
    } else {
        forcedComponent.value = null;
    }
    forcedNodeChannelId.value = null;
    pumpDrawerOpen.value = true;
}

function onContractClick(contract: CalibrationContract) {
    const target = contract.action?.target;
    if (target === 'pumps') currentSub.value = 'pumps';
    else if (target === 'sensors') currentSub.value = 'sensors';
    else if (target === 'process') currentSub.value = 'process';
    else if (target === 'correction') currentSub.value = 'correction';
    else if (target === 'pid') currentSub.value = 'pid';
}

function onBlockerNavigate(contract: CalibrationContract) {
    onContractClick(contract);
    blockersOpen.value = false;
}

async function onPumpStart(payload: PumpCalibrationRunPayload) {
    await pumpActions.startPumpCalibration(payload);
}

async function onPumpSave(payload: PumpCalibrationSavePayload) {
    const ok = await pumpActions.savePumpCalibration(payload);
    if (ok) {
        showToast('Калибровка сохранена', 'success');
        // Drawer остаётся открытым — пользователь увидит «следующий некалиброванный»
        // и сможет продолжить. Закрытие — явное (кнопка «Закрыть» или крестик).
    }
}

function onExportCsv() {
    const rows = pumps.value.map((p) => ({
        role: p.role,
        component: p.component,
        channel: `${p.node_uid}/${p.channel}`,
        ml_per_sec: p.ml_per_sec ?? '',
        k_ms_per_ml_l: p.k_ms_per_ml_l ?? '',
        valid_from: p.valid_from ?? '',
        source: p.source ?? '',
    }));
    if (rows.length === 0) {
        showToast('Нет калибровок для экспорта', 'info');
        return;
    }
    const header = Object.keys(rows[0]).join(',');
    const body = rows
        .map((r) => Object.values(r).map((v) => JSON.stringify(v ?? '')).join(','))
        .join('\n');
    const blob = new Blob([`${header}\n${body}`], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `pump-calibrations-zone-${props.zoneId}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}
</script>

<style scoped>
.cal-hub {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
}

.cal-hub__grid {
    display: grid;
    grid-template-columns: minmax(220px, 260px) 1fr;
    gap: 0.85rem;
    align-items: start;
}

.cal-hub__sidebar {
    display: flex;
    flex-direction: column;
    gap: 0.85rem;
    padding: 0.65rem;
    border: 1px solid rgba(148, 163, 184, 0.2);
    border-radius: 0.5rem;
}

.cal-hub__section {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
}

.cal-hub__section-label {
    font-size: 0.62rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    font-weight: 700;
    opacity: 0.55;
    padding: 0 0.4rem 0.25rem;
}

.cal-hub__main {
    padding: 0.85rem;
    border: 1px solid rgba(148, 163, 184, 0.2);
    border-radius: 0.5rem;
    min-height: 260px;
}

.cal-sub-basic {
    display: flex;
    flex-direction: column;
    gap: 0.85rem;
}

.cal-sub-basic__head h3 {
    font-size: 1rem;
    font-weight: 700;
    margin: 0 0 0.25rem;
}

.cal-sub-basic__desc {
    font-size: 0.78rem;
    opacity: 0.7;
}

.cal-sub-basic__pid {
    display: grid;
    gap: 0.75rem;
}

@media (max-width: 820px) {
    .cal-hub__grid {
        grid-template-columns: 1fr;
    }
}
</style>
