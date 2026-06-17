/**
 * Config Response Composable
 * 
 * Handles WebSocket events for configuration responses from ESP32 devices.
 * Listens for 'config_response' events and provides notifications and state management.
 * Uses WebSocket singleton service for efficient connection management.
 */

import { ref, onMounted, onUnmounted } from 'vue'
import { useWebSocket } from '@/composables/useWebSocket'
import type { ConfigResponse } from '@/types'
import type { WebSocketMessage } from '@/services/websocket'
import { createLogger } from '@/utils/logger'

const logger = createLogger('ConfigResponse')

// =============================================================================
// COMPOSABLE
// =============================================================================

export function useConfigResponse() {
  const lastResponse = ref<ConfigResponse | null>(null)
  
  // Event handlers
  const onSuccessHandler = ref<((response: ConfigResponse) => void) | null>(null)
  const onErrorHandler = ref<((response: ConfigResponse) => void) | null>(null)

  // WebSocket for live updates (singleton)
  const { subscribe, unsubscribe, isConnected } = useWebSocket({
    autoConnect: true,
    autoReconnect: true,
  })

  /**
   * Handle WebSocket messages for config responses
   */
  function handleWebSocketMessage(message: WebSocketMessage) {
    try {
      // Handle config_response events (server sends type: 'config_response')
      if (message.type === 'config_response') {
        const response: ConfigResponse = {
          esp_id: (message.data.esp_id as string) || '',
          config_type: (message.data.config_type as 'sensor' | 'actuator') || 'sensor',
          status: (message.data.status as 'success' | 'error') || 'error',
          count: (message.data.count as number) || 0,
          message: (message.data.message as string) || '',
          error_code: message.data.error_code as string | undefined,
          timestamp: (message.data.timestamp as number) || Date.now(),
        }
        
        lastResponse.value = response
        
        // Call appropriate handler
        if (response.status === 'success') {
          onSuccessHandler.value?.(response)
        } else {
          onErrorHandler.value?.(response)
        }
      }
    } catch (error) {
      logger.error('Failed to parse message', error)
    }
  }

  /**
   * Register success handler
   */
  function onSuccess(handler: (response: ConfigResponse) => void) {
    onSuccessHandler.value = handler
  }

  /**
   * Register error handler
   */
  function onError(handler: (response: ConfigResponse) => void) {
    onErrorHandler.value = handler
  }

  // Subscribe to config_response events on mount
  onMounted(() => {
    subscribe(
      {
        types: ['config_response'],
      },
      handleWebSocketMessage
    )
  })

  // Unsubscribe on unmount
  onUnmounted(() => {
    unsubscribe()
  })

  return {
    lastResponse,
    isConnected,
    onSuccess,
    onError,
  }
}

