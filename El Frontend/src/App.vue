<script setup lang="ts">
import { RouterView, useRoute } from 'vue-router'
import { useAuthStore } from '@/shared/stores/auth.store'
import { useEspStore } from '@/stores/esp'
import { useNotificationInboxStore } from '@/shared/stores/notification-inbox.store'
import { useAlertCenterStore } from '@/shared/stores/alert-center.store'
import { onMounted, onUnmounted, ref, watch } from 'vue'
import ToastContainer from '@/shared/design/patterns/ToastContainer.vue'
import ErrorDetailsModal from '@/components/error/ErrorDetailsModal.vue'
import type { ErrorDetailsData } from '@/components/error/ErrorDetailsModal.vue'
import ConfirmDialog from '@/shared/design/patterns/ConfirmDialog.vue'
import ContextMenu from '@/shared/design/patterns/ContextMenu.vue'
import NotificationDrawer from '@/components/notifications/NotificationDrawer.vue'

const authStore = useAuthStore()
const espStore = useEspStore()
const notificationInboxStore = useNotificationInboxStore()
const alertCenterStore = useAlertCenterStore()
const route = useRoute()

// Error Details Modal state (triggered via CustomEvent from toast actions)
const errorModalOpen = ref(false)
const errorModalData = ref<ErrorDetailsData | null>(null)

function handleShowErrorDetails(e: Event) {
  const detail = (e as CustomEvent).detail as ErrorDetailsData
  errorModalData.value = detail
  errorModalOpen.value = true
}

function initNotificationData(): void {
  notificationInboxStore.bootstrapInboxFromRoute()
  void notificationInboxStore.loadInitial()
  alertCenterStore.fetchStats()
  alertCenterStore.startStatsPolling()
}

onMounted(async () => {
  await authStore.checkAuthStatus()
  window.addEventListener('show-error-details', handleShowErrorDetails)

  if (authStore.isAuthenticated) {
    initNotificationData()
  }
})

watch(
  () => authStore.isAuthenticated,
  (isAuth) => {
    if (isAuth) {
      initNotificationData()
    } else {
      alertCenterStore.stopStatsPolling()
    }
  },
)

/** SPA-Navigation zu ?notifications=alerts (Bookmark / Teilen) */
watch(
  () => route.query.notifications,
  (raw) => {
    if (!authStore.isAuthenticated) return
    const v = Array.isArray(raw) ? raw[0] : raw
    if (v === 'alerts' && !notificationInboxStore.isDrawerOpen) {
      notificationInboxStore.applyNotificationsRouteDeepLink()
    }
  },
)

onUnmounted(() => {
  espStore.cleanupWebSocket()
  alertCenterStore.stopStatsPolling()
  window.removeEventListener('show-error-details', handleShowErrorDetails)
})
</script>

<template>
  <RouterView />
  <NotificationDrawer />
  <ToastContainer />
  <ConfirmDialog />
  <ContextMenu />
  <ErrorDetailsModal
    :error="errorModalData"
    :open="errorModalOpen"
    @close="errorModalOpen = false"
  />
</template>
