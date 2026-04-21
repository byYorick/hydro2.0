import { apiGet, apiPost } from './_client';
import type { GrowCycleLaunchPayload } from '@/schemas/growCycleLaunch';

export interface LaunchFlowStep {
    id: string;
    title: string;
    description?: string;
    visible: boolean;
    required: boolean;
    depends_on?: string[];
    validation?: { required_fields?: string[] };
}

export interface LaunchFlowReadinessBlocker {
    code: string;
    message: string;
    severity: 'error' | 'warning' | 'info';
    action?: {
        type: string;
        label?: string;
        role?: string;
        pid_type?: string;
        mode?: string;
        route?: { name: string; params?: Record<string, unknown> };
    };
}

export interface LaunchFlowReadiness {
    ready: boolean;
    blockers: LaunchFlowReadinessBlocker[];
    warnings: string[];
}

export interface LaunchFlowManifest {
    zone_id: number | null;
    role: string | null;
    steps: LaunchFlowStep[];
    role_hints: Record<string, string[]>;
    readiness: LaunchFlowReadiness;
}

export interface GrowCycleLaunchResponse {
    grow_cycle_id: number;
    status: string;
}

export const launchFlowApi = {
    async getManifest(zoneId: number | null): Promise<LaunchFlowManifest> {
        const query = zoneId ? `?zone_id=${encodeURIComponent(String(zoneId))}` : '';
        return apiGet<LaunchFlowManifest>(`/api/launch-flow/manifest${query}`);
    },

    async launch(payload: GrowCycleLaunchPayload): Promise<GrowCycleLaunchResponse> {
        const { zone_id: zoneId, overrides: _overrides, bindings: _bindings, ...core } = payload;

        const body: Record<string, unknown> = {
            ...core,
            start_immediately: true,
        };

        return apiPost<GrowCycleLaunchResponse>(`/api/zones/${zoneId}/grow-cycles`, body);
    },
};
