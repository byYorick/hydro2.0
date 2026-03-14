import { useApi } from '@/composables/useApi'
import type { SensorCalibration, SensorCalibrationOverview } from '@/types/SensorCalibration'

export function useSensorCalibration(zoneId: number) {
  const { api } = useApi()

  async function fetchStatus(): Promise<SensorCalibrationOverview[]> {
    const response = await api.get(`/api/zones/${zoneId}/sensor-calibrations/status`)
    return response.data.data as SensorCalibrationOverview[]
  }

  async function fetchHistory(options: { sensorType?: string; nodeChannelId?: number; limit?: number } = {}): Promise<SensorCalibration[]> {
    const response = await api.get(`/api/zones/${zoneId}/sensor-calibrations`, {
      params: {
        sensor_type: options.sensorType,
        node_channel_id: options.nodeChannelId,
        limit: options.limit ?? 20,
      },
    })
    return response.data.data as SensorCalibration[]
  }

  async function getCalibration(calibrationId: number): Promise<SensorCalibration> {
    const response = await api.get(`/api/zones/${zoneId}/sensor-calibrations/${calibrationId}`)
    return response.data.data as SensorCalibration
  }

  async function startCalibration(nodeChannelId: number, sensorType: 'ph' | 'ec'): Promise<{ calibration: SensorCalibration; defaults: { point_1_value: number; point_2_value: number } }> {
    const response = await api.post(`/api/zones/${zoneId}/sensor-calibrations`, {
      node_channel_id: nodeChannelId,
      sensor_type: sensorType,
    })
    return response.data.data as { calibration: SensorCalibration; defaults: { point_1_value: number; point_2_value: number } }
  }

  async function submitPoint(calibrationId: number, stage: 1 | 2, referenceValue: number): Promise<SensorCalibration> {
    const response = await api.post(`/api/zones/${zoneId}/sensor-calibrations/${calibrationId}/point`, {
      stage,
      reference_value: referenceValue,
    })
    return response.data.data as SensorCalibration
  }

  async function cancelCalibration(calibrationId: number): Promise<void> {
    await api.post(`/api/zones/${zoneId}/sensor-calibrations/${calibrationId}/cancel`)
  }

  return {
    fetchStatus,
    fetchHistory,
    getCalibration,
    startCalibration,
    submitPoint,
    cancelCalibration,
  }
}
