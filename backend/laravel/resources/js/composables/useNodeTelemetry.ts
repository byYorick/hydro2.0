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
  let lastAcceptedServerTs: number | null = null
  const lastAcceptedTelemetryTsBySeries = new Map<string, number>()

  const resolveRefNumber = (value: Ref<number | null> | number | null): number | null => {
    return isRef(value) ? value.value : value
  }

  const resolveCurrentNodeId = (): number | null => {
    return resolveRefNumber(nodeId)
  }

  const toOptionalNumber = (value: unknown): number | undefined => {
    if (typeof value === 'number' && Number.isFinite(value)) {
      return value
    }

    if (typeof value === 'string' && value.trim() !== '') {
      const parsed = Number(value)
      if (Number.isFinite(parsed)) {
        return parsed
      }
    }

    return undefined
  }

  const getTelemetrySeriesKey = (data: NodeTelemetryData): string => {
    return `${data.node_id}:${data.channel ?? 'null'}:${data.metric_type}`
  }

  const resetMonotonicGuards = (): void => {
    lastAcceptedServerTs = null
    lastAcceptedTelemetryTsBySeries.clear()
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

            const eventServerTs = toOptionalNumber(payload.server_ts)
            if (
              typeof eventServerTs === 'number' &&
              typeof lastAcceptedServerTs === 'number' &&
              eventServerTs < lastAcceptedServerTs
            ) {
              logger.debug('[useNodeTelemetry] Ignoring stale telemetry batch by server_ts', {
                eventServerTs,
                lastAcceptedServerTs,
              })
              return
            }

            const updates = parseNodeTelemetryBatch(payload)
            const currentNodeId = resolveCurrentNodeId()
            let acceptedBatch = false

            updates.forEach((data) => {
              if (currentNodeId && data.node_id === currentNodeId) {
                const seriesKey = getTelemetrySeriesKey(data)
                const lastAcceptedSeriesTs = lastAcceptedTelemetryTsBySeries.get(seriesKey)
                if (
                  typeof lastAcceptedSeriesTs === 'number' &&
                  data.ts <= lastAcceptedSeriesTs
                ) {
                  logger.debug('[useNodeTelemetry] Ignoring stale telemetry point by sample ts', {
                    nodeId: currentNodeId,
                    channel: data.channel,
                    metric: data.metric_type,
                    sampleTs: data.ts,
                    lastAcceptedSeriesTs,
                  })
                  return
                }

                logger.debug('[useNodeTelemetry] Processing telemetry for node', {
                  nodeId: currentNodeId,
                  channel: data.channel,
                  metric: data.metric_type,
                  value: data.value,
                })
                try {
                  telemetryHandler(data)
                  acceptedBatch = true
                  lastAcceptedTelemetryTsBySeries.set(seriesKey, data.ts)
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

            if (
              acceptedBatch &&
              typeof eventServerTs === 'number' &&
              (lastAcceptedServerTs === null || eventServerTs > lastAcceptedServerTs)
            ) {
              lastAcceptedServerTs = eventServerTs
            }
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
    resetMonotonicGuards()
    attachChannel()

    return () => {
      unsubscribe()
    }
  }

  const unsubscribe = (): void => {
    activeHandler = null
    detachChannel()
    resetMonotonicGuards()
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
