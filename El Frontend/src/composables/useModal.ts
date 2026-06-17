import { ref } from 'vue'

/**
 * Composable for managing modal state
 *
 * @example
 * const { isOpen, open, close, toggle } = useModal()
 *
 * // In template:
 * <Modal :open="isOpen" @close="close" title="My Modal">
 *   ...
 * </Modal>
 */
export function useModal(initialState = false) {
  const isOpen = ref(initialState)

  function open() {
    isOpen.value = true
  }

  function close() {
    isOpen.value = false
  }

  function toggle() {
    isOpen.value = !isOpen.value
  }

  return {
    isOpen,
    open,
    close,
    toggle,
  }
}

/**
 * Composable for managing multiple modals
 *
 * @example
 * const modals = useModals(['addSensor', 'addActuator', 'batchUpdate'])
 *
 * modals.open('addSensor')
 * modals.close('addSensor')
 * modals.isOpen('addSensor') // ref<boolean>
 */
export function useModals<T extends string>(modalNames: T[]) {
  const state = ref<Record<T, boolean>>(
    modalNames.reduce((acc, name) => ({ ...acc, [name]: false }), {} as Record<T, boolean>)
  )

  function open(name: T) {
    state.value[name] = true
  }

  function close(name: T) {
    state.value[name] = false
  }

  function toggle(name: T) {
    state.value[name] = !state.value[name]
  }

  function closeAll() {
    modalNames.forEach(name => {
      state.value[name] = false
    })
  }

  function isOpen(name: T): boolean {
    return state.value[name]
  }

  return {
    state,
    open,
    close,
    toggle,
    closeAll,
    isOpen,
  }
}

export default useModal
