import { toValue, type MaybeRefOrGetter } from 'vue'
import { api } from '@/services/api'
import type {
  SensorCalibration,
  SensorCalibrationOverview,
  SensorCalibrationStartResult,
} from '@/types/SensorCalibration'

/**
 * @param zoneId — ref/getter/число; API всегда использует актуальное значение при вызове метода.
 */
export function useSensorCalibration(zoneId: MaybeRefOrGetter<number>) {
  function z(): number {
    return toValue(zoneId)
  }

  async function fetchStatus(): Promise<SensorCalibrationOverview[]> {
    return api.zones.sensorCalibrationStatus(z())
  }

  async function fetchHistory(options: { sensorType?: string; nodeChannelId?: number; limit?: number } = {}): Promise<SensorCalibration[]> {
    return api.zones.sensorCalibrationsList(z(), {
      sensor_type: options.sensorType,
      node_channel_id: options.nodeChannelId,
      limit: options.limit ?? 20,
    })
  }

  async function getCalibration(calibrationId: number): Promise<SensorCalibration> {
    return api.zones.sensorCalibration(z(), calibrationId)
  }

  async function startCalibration(
    nodeChannelId: number,
    sensorType: 'ph' | 'ec',
  ): Promise<SensorCalibrationStartResult> {
    return api.zones.sensorCalibrationStart(z(), {
      node_channel_id: nodeChannelId,
      sensor_type: sensorType,
    })
  }

  async function submitPoint(calibrationId: number, stage: 1 | 2, referenceValue: number): Promise<SensorCalibration> {
    return api.zones.sensorCalibrationAddPoint(z(), calibrationId, {
      stage,
      reference_value: referenceValue,
    })
  }

  async function cancelCalibration(calibrationId: number): Promise<void> {
    await api.zones.sensorCalibrationCancel(z(), calibrationId)
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
