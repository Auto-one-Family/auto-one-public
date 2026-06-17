import { ref, watch, onMounted, onUnmounted, type Ref } from 'vue'
import { useSwipe } from '@vueuse/core'

export interface SwipeNavigationOptions {
  /** Minimum swipe distance in pixels to trigger action */
  threshold?: number
  /** Callback when swiping left (e.g., close sidebar) */
  onSwipeLeft?: () => void
  /** Callback when swiping right (e.g., open sidebar) */
  onSwipeRight?: () => void
  /** Callback when swiping up */
  onSwipeUp?: () => void
  /** Callback when swiping down */
  onSwipeDown?: () => void
  /** Whether to prevent default touch behavior */
  preventDefault?: boolean
}

/**
 * Composable for handling swipe gestures on mobile devices
 *
 * @example
 * const sidebarElement = ref<HTMLElement | null>(null)
 * const { isSwiping, direction } = useSwipeNavigation(sidebarElement, {
 *   onSwipeLeft: () => emit('close'),
 *   threshold: 50
 * })
 */
export function useSwipeNavigation(
  element: Ref<HTMLElement | null | undefined>,
  options: SwipeNavigationOptions = {}
) {
  const {
    threshold = 50,
    onSwipeLeft,
    onSwipeRight,
    onSwipeUp,
    onSwipeDown,
    preventDefault = false,
  } = options

  const { direction, isSwiping, lengthX, lengthY } = useSwipe(element, {
    passive: !preventDefault,
    threshold,
  })

  // Track if a swipe action was triggered
  const swipeTriggered = ref(false)

  // Watch for direction changes and trigger callbacks
  watch(
    () => [isSwiping.value, direction.value] as const,
    ([swiping, dir]) => {
      if (!swiping && dir && !swipeTriggered.value) {
        // Check if swipe distance exceeds threshold
        const distance = dir === 'left' || dir === 'right'
          ? Math.abs(lengthX.value)
          : Math.abs(lengthY.value)

        if (distance >= threshold) {
          swipeTriggered.value = true

          switch (dir) {
            case 'left':
              onSwipeLeft?.()
              break
            case 'right':
              onSwipeRight?.()
              break
            case 'up':
              onSwipeUp?.()
              break
            case 'down':
              onSwipeDown?.()
              break
          }
        }
      } else if (swiping) {
        // Reset triggered flag when starting a new swipe
        swipeTriggered.value = false
      }
    }
  )

  return {
    isSwiping,
    direction,
    lengthX,
    lengthY,
  }
}

/**
 * Simple sidebar swipe handler - closes sidebar on left swipe
 *
 * @example
 * const sidebarElement = ref<HTMLElement | null>(null)
 * useSidebarSwipe(sidebarElement, () => emit('close'))
 */
export function useSidebarSwipe(
  element: Ref<HTMLElement | null | undefined>,
  onClose: () => void
) {
  return useSwipeNavigation(element, {
    onSwipeLeft: onClose,
    threshold: 50,
  })
}

/**
 * Edge swipe to open sidebar (swipe from left edge of screen)
 *
 * @example
 * const { canOpen } = useEdgeSwipe(() => emit('open-sidebar'))
 */
export function useEdgeSwipe(onOpen: () => void, edgeWidth = 20) {
  const touchStartX = ref(0)
  const isEdgeSwipe = ref(false)

  function handleTouchStart(e: TouchEvent) {
    const touch = e.touches[0]
    touchStartX.value = touch.clientX
    isEdgeSwipe.value = touch.clientX <= edgeWidth
  }

  function handleTouchEnd(e: TouchEvent) {
    if (!isEdgeSwipe.value) return

    const touch = e.changedTouches[0]
    const deltaX = touch.clientX - touchStartX.value

    // If swiped right from edge by at least 50px
    if (deltaX >= 50) {
      onOpen()
    }

    isEdgeSwipe.value = false
  }

  onMounted(() => {
    document.addEventListener('touchstart', handleTouchStart, { passive: true })
    document.addEventListener('touchend', handleTouchEnd, { passive: true })
  })

  onUnmounted(() => {
    document.removeEventListener('touchstart', handleTouchStart)
    document.removeEventListener('touchend', handleTouchEnd)
  })

  return {
    isEdgeSwipe,
  }
}

export default useSwipeNavigation
