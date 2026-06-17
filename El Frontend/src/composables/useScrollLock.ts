/**
 * useScrollLock — Reference-counted body scroll lock.
 * Prevents race conditions when multiple modals/overlays are open simultaneously.
 * When all consumers unlock, scroll is restored.
 */

let lockCount = 0

export function useScrollLock() {
  let isLocked = false

  function lock() {
    if (isLocked) return
    isLocked = true
    lockCount++
    if (lockCount === 1) {
      document.body.style.overflow = 'hidden'
    }
  }

  function unlock() {
    if (!isLocked) return
    isLocked = false
    lockCount--
    if (lockCount === 0) {
      document.body.style.overflow = ''
    }
  }

  return { lock, unlock }
}
