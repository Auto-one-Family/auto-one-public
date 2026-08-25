<script setup lang="ts">
/**
 * DomainAuswertungView — domänen-gruppierte Auswertungs-Sicht (AUT-1321).
 *
 * Read-only. Domäne = primäre Achse, Zone = optionaler Filter (Default alle).
 * Kein Aktor-Store, kein Steuer-/Regel-Bezug, kein zweites Lagebild.
 *
 * Erwartungssteuerung: Struktur + Discoverability; Befund-Slot v1 leer.
 */

import { computed, onMounted, ref } from 'vue'
import { Layers } from 'lucide-vue-next'
import { useEspStore } from '@/stores/esp'
import { useZoneStore } from '@/shared/stores/zone.store'
import { useTankStore } from '@/shared/stores/tank.store'
import { useToast } from '@/composables/useToast'
import BaseSelect from '@/shared/design/primitives/BaseSelect.vue'
import BaseSpinner from '@/shared/design/primitives/BaseSpinner.vue'
import ErrorState from '@/shared/design/patterns/ErrorState.vue'
import DomainGapBanner, {
  type DomainGapItem,
} from '@/components/domains/DomainGapBanner.vue'
import DomainSection from '@/components/domains/DomainSection.vue'
import {
  DEVICE_DOMAIN_KEYS,
  getDomainLabel,
  type DeviceDomainKey,
} from '@/components/domains/domainLabels'
import type { StructureDeviceRef } from '@/components/domains/DomainStructureBlock.vue'
import type { Tank } from '@/types'

const espStore = useEspStore()
const zoneStore = useZoneStore()
const tankStore = useTankStore()
const toast = useToast()

const loading = ref(true)
const error = ref<string | null>(null)
const zoneFilter = ref('')
const expandedDomains = ref<Record<string, boolean>>({
  luft: true,
})

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    await Promise.all([
      espStore.fetchAll(),
      zoneStore.fetchZoneEntities('active'),
      tankStore.fetchTanks(),
    ])
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Laden fehlgeschlagen'
    toast.error('Domänen-Auswertung konnte nicht geladen werden')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void load()
})

const zoneOptions = computed(() => [
  { value: '', label: 'Alle Zonen' },
  ...zoneStore.activeZones.map((z) => ({
    value: z.zone_id,
    label: z.name?.trim() || 'Ort ohne Namen',
  })),
])

const zoneNames = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {}
  for (const z of zoneStore.activeZones) {
    map[z.zone_id] = z.name?.trim() || 'Ort ohne Namen'
  }
  return map
})

function deviceIdOf(device: (typeof espStore.devices)[number]): string {
  return espStore.getDeviceId(device)
}

function matchesZoneFilter(device: (typeof espStore.devices)[number]): boolean {
  if (!zoneFilter.value) return true
  return device.zone_id === zoneFilter.value
}

function devicesForDomain(domainKey: DeviceDomainKey): StructureDeviceRef[] {
  return espStore.devices
    .filter((d) => d.domain === domainKey && matchesZoneFilter(d))
    .map((device) => ({
      device,
      deviceId: deviceIdOf(device),
    }))
}

function tanksForWasser(): Tank[] {
  const devices = devicesForDomain('wasser')
  const tankIds = new Set(
    devices
      .map((d) => d.device.tank_id)
      .filter((id): id is string => typeof id === 'string' && id.length > 0),
  )
  return tankStore.tanks.filter((t) => {
    if (!tankIds.has(t.id)) return false
    if (!zoneFilter.value) return true
    return t.zone_id === zoneFilter.value
  })
}

/** Sorted, stable zone-id lists per domain — avoids Ist-reload on store churn. */
const zoneIdsByDomain = computed(() => {
  const map = {} as Record<DeviceDomainKey, string[]>
  for (const domainKey of DEVICE_DOMAIN_KEYS) {
    const ids = new Set<string>()
    for (const { device } of devicesForDomain(domainKey)) {
      if (device.zone_id) ids.add(device.zone_id)
    }
    map[domainKey] = [...ids].sort()
  }
  return map
})

function zoneIdsForDomain(domainKey: DeviceDomainKey): string[] {
  return zoneIdsByDomain.value[domainKey] ?? []
}

const gaps = computed<DomainGapItem[]>(() => {
  const items: DomainGapItem[] = []
  for (const device of espStore.devices) {
    if (!matchesZoneFilter(device)) continue
    const id = deviceIdOf(device)
    const name = device.name?.trim() || 'Gerät ohne Namen'
    if (!device.domain) {
      items.push({ deviceId: id, deviceName: name, kind: 'missing_domain' })
      continue
    }
    if (device.domain === 'wasser' && !device.tank_id) {
      items.push({ deviceId: id, deviceName: name, kind: 'wasser_without_tank' })
    }
  }
  return items
})

function toggleDomain(domainKey: string): void {
  expandedDomains.value = {
    ...expandedDomains.value,
    [domainKey]: !expandedDomains.value[domainKey],
  }
}

function isExpanded(domainKey: string): boolean {
  return !!expandedDomains.value[domainKey]
}
</script>

<template>
  <div class="mx-auto max-w-5xl space-y-6 p-4 md:p-6">
    <header class="space-y-2">
      <div class="flex items-center gap-2">
        <Layers class="h-6 w-6 text-[var(--color-iridescent-1)]" aria-hidden="true" />
        <h1 class="text-2xl font-semibold text-dark-50">Domänen</h1>
      </div>
      <p class="max-w-2xl text-sm text-dark-300">
        Auswertungs-Bereich nach Domäne — Mess-Struktur und Discoverability.
        Kein Lagebild und keine Steuerung. Befunde folgen später je Abschnitt.
      </p>
    </header>

    <div class="max-w-xs">
      <BaseSelect
        v-model="zoneFilter"
        :options="zoneOptions"
        label="Zone filtern"
      />
    </div>

    <div v-if="loading" class="flex items-center gap-2 text-sm text-dark-300">
      <BaseSpinner class="h-5 w-5" />
      <span>Domänen werden geladen…</span>
    </div>

    <ErrorState
      v-else-if="error"
      :message="error"
      @retry="load"
    />

    <template v-else>
      <DomainGapBanner :gaps="gaps" />

      <div class="space-y-4">
        <DomainSection
          v-for="domainKey in DEVICE_DOMAIN_KEYS"
          :key="domainKey"
          :domain-key="domainKey"
          :domain-label="getDomainLabel(domainKey)"
          :expanded="isExpanded(domainKey)"
          :devices="devicesForDomain(domainKey)"
          :tanks="domainKey === 'wasser' ? tanksForWasser() : []"
          :zone-ids="zoneIdsForDomain(domainKey)"
          :zone-names="zoneNames"
          @toggle="toggleDomain(domainKey)"
        />
      </div>
    </template>
  </div>
</template>
