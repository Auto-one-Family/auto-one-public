<script setup lang="ts">
/**
 * CalibrationView
 *
 * Wrapper view for the CalibrationWizard component.
 * Route: /calibration
 *
 * P1c (AUT-490): Deep-Link support — reads espId/gpio/sensorType/skipSelect from
 * URL query params and forwards them to CalibrationWizard as props, so that
 * SensorConfigPanel.openCalibrationWizard() can open the wizard pre-configured
 * for a specific sensor (route: /calibration?espId=X&gpio=Y&sensorType=Z&skipSelect=1).
 */
import { ref, computed, onMounted } from 'vue'
import { useRoute, onBeforeRouteLeave } from 'vue-router'
import CalibrationWizard from '@/components/calibration/CalibrationWizard.vue'
import { useEspStore } from '@/stores/esp'

type CalibrationWizardExpose = {
  confirmLeave?: () => Promise<boolean>
}

const route = useRoute()
const espStore = useEspStore()
const wizardRef = ref<CalibrationWizardExpose | null>(null)

// P1c: Parse deep-link query params from URL
// SensorConfigPanel pushes: { path: '/calibration', query: { espId, gpio, sensorType, skipSelect: '1' } }
const deepLinkEspId = computed<string | undefined>(() => {
  const v = route.query.espId
  return typeof v === 'string' && v.length > 0 ? v : undefined
})

const deepLinkGpio = computed<number | undefined>(() => {
  const v = route.query.gpio
  const parsed = typeof v === 'string' ? parseInt(v, 10) : NaN
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : undefined
})

const deepLinkSensorType = computed<string | undefined>(() => {
  const v = route.query.sensorType
  return typeof v === 'string' && v.length > 0 ? v : undefined
})

const deepLinkSkipSelect = computed<boolean>(() => {
  return route.query.skipSelect === '1' || route.query.skipSelect === 'true'
})

onMounted(() => {
  if (espStore.devices.length === 0) {
    espStore.fetchAll()
  }
})

onBeforeRouteLeave(async () => {
  if (!wizardRef.value?.confirmLeave) {
    return true
  }
  return wizardRef.value.confirmLeave()
})
</script>

<template>
  <div class="calibration-view">
    <CalibrationWizard
      ref="wizardRef"
      :esp-id="deepLinkEspId"
      :gpio="deepLinkGpio"
      :sensor-type="deepLinkSensorType"
      :skip-select="deepLinkSkipSelect"
    />
  </div>
</template>

<style scoped>
.calibration-view {
  padding: 1.5rem;
  max-width: 720px;
  margin: 0 auto;
}
</style>
