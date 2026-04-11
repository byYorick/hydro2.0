import { api } from '@/services/api'
import type { SensorCalibration, SensorCalibrationOverview } from '@/types/SensorCalibration'

export function useSensorCalibration(zoneId: number) {
  async function fetchStatus(): Promise<SensorCalibrationOverview[]> {
    const response = await api.zones.sensorCalibrationStatus(zoneId) as { data?: SensorCalibrationOverview[] } | SensorCalibrationOverview[]
    if (Array.isArray(response)) return response
    return (response?.data as SensorCalibrationOverview[]) ?? []
  }

  async function fetchHistory(options: { sensorType?: string; nodeChannelId?: number; limit?: number } = {}): Promise<SensorCalibration[]> {
    const response = await api.zones.sensorCalibrationsList(zoneId, {
      sensor_type: options.sensorType,
      node_channel_id: options.nodeChannelId,
      limit: options.limit ?? 20,
    }) as { data?: SensorCalibration[] } | SensorCalibration[]
    if (Array.isArray(response)) return response
    return (response?.data as SensorCalibration[]) ?? []
  }

  async function getCalibration(calibrationId: number): Promise<SensorCalibration> {
    const response = await api.zones.sensorCalibration(zoneId, calibrationId) as { data?: SensorCalibration } | SensorCalibration
    return ((response as { data?: SensorCalibration })?.data ?? response) as SensorCalibration
  }

  async function startCalibration(
    nodeChannelId: number,
    sensorType: 'ph' | 'ec',
  ): Promise<{ calibration: SensorCalibration; defaults: { point_1_value: number; point_2_value: number } }> {
    const response = await api.zones.sensorCalibrationStart(zoneId, {
      node_channel_id: nodeChannelId,
      sensor_type: sensorType,
    }) as { data?: { calibration: SensorCalibration; defaults: { point_1_value: number; point_2_value: number } } }
    return response.data ?? (response as never)
  }

  async function submitPoint(calibrationId: number, stage: 1 | 2, referenceValue: number): Promise<SensorCalibration> {
    const response = await api.zones.sensorCalibrationAddPoint(zoneId, calibrationId, {
      stage,
      reference_value: referenceValue,
    }) as { data?: SensorCalibration }
    return (response.data ?? response) as SensorCalibration
  }

  async function cancelCalibration(calibrationId: number): Promise<void> {
    await api.zones.sensorCalibrationCancel(zoneId, calibrationId)
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
