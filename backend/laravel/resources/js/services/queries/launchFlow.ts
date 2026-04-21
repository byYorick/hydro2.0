import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query';
import { computed, type ComputedRef } from 'vue';
import { launchFlowApi, type LaunchFlowManifest } from '@/services/api/launchFlow';
import type { GrowCycleLaunchPayload } from '@/schemas/growCycleLaunch';

export const launchFlowKeys = {
    all: ['launch-flow'] as const,
    manifest: (zoneId: number | null) => [...launchFlowKeys.all, 'manifest', zoneId] as const,
    readiness: (zoneId: number | null) => [...launchFlowKeys.all, 'readiness', zoneId] as const,
};

export function useLaunchManifest(
    zoneIdRef: ComputedRef<number | null> | { value: number | null },
) {
    const query = useQuery<LaunchFlowManifest>({
        queryKey: computed(() => launchFlowKeys.manifest(zoneIdRef.value)),
        queryFn: () => launchFlowApi.getManifest(zoneIdRef.value),
        staleTime: 15_000,
    });
    return query;
}

export function useLaunchReadiness(
    zoneIdRef: ComputedRef<number | null> | { value: number | null },
) {
    const query = useQuery({
        queryKey: computed(() => launchFlowKeys.readiness(zoneIdRef.value)),
        queryFn: async () => {
            const manifest = await launchFlowApi.getManifest(zoneIdRef.value);
            return manifest.readiness;
        },
        enabled: computed(() => zoneIdRef.value !== null),
        staleTime: 5_000,
    });
    return query;
}

export function useLaunchGrowCycleMutation() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: GrowCycleLaunchPayload) => launchFlowApi.launch(payload),
        onSuccess: async (_data, variables) => {
            await queryClient.invalidateQueries({
                queryKey: launchFlowKeys.manifest(variables.zone_id),
            });
            await queryClient.invalidateQueries({
                queryKey: launchFlowKeys.readiness(variables.zone_id),
            });
        },
    });
}
