import { ref, onUnmounted, type Ref } from 'vue'
import { logger } from '@/utils/logger'
import { getEchoInstance } from '@/utils/echoClient'
import { readBooleanEnv } from '@/utils/env'

export interface NodeTelemetryData {
  node_id: number
  channel: string
  metric_type: string
  value: number
  ts: number
}

type TelemetryHandler = (data: NodeTelemetryData) => void

/**
 * Composable для подписки на real-time телеметрию устройства через WebSocket
 */
export function useNodeTelemetry(nodeId: Ref<number | null> | number | null) {
  const isSubscribed = ref(false)
  let echoChannel: any = null
  let handlerRef: ((payload: any) => void) | null = null

  const subscribe = (handler: TelemetryHandler): (() => void) => {
    const nodeIdValue = typeof nodeId === 'object' && nodeId !== null ? nodeId.value : nodeId
    
    if (!nodeIdValue) {
      logger.warn('[useNodeTelemetry] Cannot subscribe: nodeId is null')
      return () => {}
    }

    const wsEnabled = readBooleanEnv('VITE_ENABLE_WS', true)
    if (!wsEnabled) {
      logger.debug('[useNodeTelemetry] WebSocket disabled, skipping subscription')
      return () => {}
    }

    const echo = getEchoInstance()
    if (!echo) {
      logger.warn('[useNodeTelemetry] Echo not available, subscription failed')
      return () => {}
    }

    try {
      // Подписываемся на канал устройств
      echoChannel = echo.private('hydro.devices')
      
      // Создаем обработчик события
      // Используем функцию для получения актуального значения nodeId (если это ref)
      handlerRef = (payload: any) => {
        logger.debug('[useNodeTelemetry] Received telemetry event', {
          payload,
          expectedNodeId: typeof nodeId === 'object' && nodeId !== null ? nodeId.value : nodeId,
        })
        
        const data = payload as NodeTelemetryData
        
        // Получаем актуальное значение nodeId (на случай если это ref)
        const currentNodeId = typeof nodeId === 'object' && nodeId !== null ? nodeId.value : nodeId
        
        // Фильтруем только телеметрию для нужного устройства
        if (currentNodeId && data.node_id === currentNodeId) {
          logger.debug('[useNodeTelemetry] Processing telemetry for node', {
            nodeId: currentNodeId,
            channel: data.channel,
            metric: data.metric_type,
            value: data.value,
          })
          try {
            handler(data)
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
      }

      // Подписываемся на событие телеметрии
      // Когда используется broadcastAs(), нужно использовать имя из broadcastAs() с префиксом точки
      echoChannel.listen('.node.telemetry.updated', handlerRef)
      
      isSubscribed.value = true
      logger.info('[useNodeTelemetry] Subscribed to node telemetry', {
        nodeId: nodeIdValue,
        channel: 'hydro.devices',
        event: '.node.telemetry.updated',
      })

      // Возвращаем функцию отписки
      return () => {
        unsubscribe()
      }
    } catch (err) {
      logger.error('[useNodeTelemetry] Subscription error', {
        error: err instanceof Error ? err.message : String(err),
        nodeId: nodeIdValue,
      })
      return () => {}
    }
  }

  const unsubscribe = (): void => {
    if (echoChannel && handlerRef) {
      try {
        echoChannel.stopListening('.node.telemetry.updated', handlerRef)
        logger.debug('[useNodeTelemetry] Unsubscribed from node telemetry')
      } catch (err) {
        logger.warn('[useNodeTelemetry] Error during unsubscribe', {
          error: err instanceof Error ? err.message : String(err),
        })
      }
    }
    
    echoChannel = null
    handlerRef = null
    isSubscribed.value = false
  }

  // Автоматическая отписка при размонтировании
  onUnmounted(() => {
    unsubscribe()
  })

  return {
    subscribe,
    unsubscribe,
    isSubscribed: () => isSubscribed.value,
  }
}

