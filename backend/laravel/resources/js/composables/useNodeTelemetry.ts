import { ref, onUnmounted, isRef, type Ref } from 'vue'
import { logger } from '@/utils/logger'
import { readBooleanEnv } from '@/utils/env'
import { subscribeManagedChannelEvents } from '@/ws/managedChannelEvents'
import { parseNodeTelemetryBatch } from '@/ws/nodeTelemetryPayload'

export interface NodeTelemetryData {
  node_id: number
  channel: string | null
  metric_type: string
  value: number
  ts: number
}

type TelemetryHandler = (data: NodeTelemetryData) => void

/**
 * Composable для подписки на real-time телеметрию устройства через WebSocket.
 * Канонический reconnect/resubscribe живёт в managedChannelEvents.
 */
export function useNodeTelemetry(
  nodeId: Ref<number | null> | number | null,
  zoneId: Ref<number | null> | number | null,
) {
  const isSubscribed = ref(false)
  let activeHandler: TelemetryHandler | null = null
  let stopTelemetrySubscription: (() => void) | null = null

  const resolveRefNumber = (value: Ref<number | null> | number | null): number | null => {
    return isRef(value) ? value.value : value
  }

  const resolveCurrentNodeId = (): number | null => {
    return resolveRefNumber(nodeId)
  }

  const detachChannel = (): void => {
    if (stopTelemetrySubscription) {
      try {
        stopTelemetrySubscription()
        logger.debug('[useNodeTelemetry] Unsubscribed from node telemetry')
      } catch (err) {
        logger.warn('[useNodeTelemetry] Error during unsubscribe', {
          error: err instanceof Error ? err.message : String(err),
        })
      }
      stopTelemetrySubscription = null
    }

    isSubscribed.value = false
  }

  const attachChannel = (): boolean => {
    const nodeIdValue = resolveCurrentNodeId()
    const zoneIdValue = resolveRefNumber(zoneId)
    const telemetryHandler = activeHandler

    if (!nodeIdValue || !zoneIdValue || !telemetryHandler) {
      logger.warn('[useNodeTelemetry] Cannot subscribe: nodeId or zoneId is null', {
        nodeId: nodeIdValue,
        zoneId: zoneIdValue,
        hasHandler: !!telemetryHandler,
      })
      return false
    }

    const wsEnabled = readBooleanEnv('VITE_ENABLE_WS', true)
    if (!wsEnabled) {
      logger.debug('[useNodeTelemetry] WebSocket disabled, skipping subscription')
      return false
    }

    try {
      const channelName = `hydro.zones.${zoneIdValue}`
      stopTelemetrySubscription = subscribeManagedChannelEvents({
        channelName,
        componentTag: `useNodeTelemetry:${zoneIdValue}:${nodeIdValue}`,
        eventHandlers: {
          '.telemetry.batch.updated': (payload) => {
            logger.debug('[useNodeTelemetry] Received telemetry event', {
              payload,
              expectedNodeId: resolveCurrentNodeId(),
            })

            const updates = parseNodeTelemetryBatch(payload)
            const currentNodeId = resolveCurrentNodeId()

            updates.forEach((data) => {
              if (currentNodeId && data.node_id === currentNodeId) {
                logger.debug('[useNodeTelemetry] Processing telemetry for node', {
                  nodeId: currentNodeId,
                  channel: data.channel,
                  metric: data.metric_type,
                  value: data.value,
                })
                try {
                  telemetryHandler(data)
                } catch (err) {
                  logger.error('[useNodeTelemetry] Handler error', {
                    error: err instanceof Error ? err.message : String(err),
                    nodeId: currentNodeId,
                  })
                }
              } else {
                logger.debug('[useNodeTelemetry] Ignoring telemetry (nodeId mismatch)', {
                  receivedNodeId: data.node_id,
                  expectedNodeId: currentNodeId,
                })
              }
            })
          },
        },
      })

      isSubscribed.value = true
      logger.info('[useNodeTelemetry] Subscribed to node telemetry', {
        nodeId: nodeIdValue,
        zoneId: zoneIdValue,
        channel: `hydro.zones.${zoneIdValue}`,
        event: '.telemetry.batch.updated',
      })

      return true
    } catch (err) {
      logger.error('[useNodeTelemetry] Subscription error', {
        error: err instanceof Error ? err.message : String(err),
        nodeId: nodeIdValue,
      })
      stopTelemetrySubscription = null
      isSubscribed.value = false
      return false
    }
  }

  const subscribe = (handler: TelemetryHandler): (() => void) => {
    activeHandler = handler
    detachChannel()
    attachChannel()

    return () => {
      unsubscribe()
    }
  }

  const unsubscribe = (): void => {
    activeHandler = null
    detachChannel()
  }

  onUnmounted(() => {
    unsubscribe()
  })

  return {
    subscribe,
    unsubscribe,
    isSubscribed: () => isSubscribed.value,
  }
}
