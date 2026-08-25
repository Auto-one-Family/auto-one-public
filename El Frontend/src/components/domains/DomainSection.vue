<script setup lang="ts">
/**
 * DomainSection — one domain: header + three separated blocks (AUT-1321).
 * Struktur ≠ Ist (lazy) ≠ Befund-Slot (v1 empty).
 */

import { ref } from 'vue'
import { ChevronDown, ChevronRight } from 'lucide-vue-next'
import DomainStructureBlock, {
  type DomainStructureRow,
  type StructureDeviceRef,
} from '@/components/domains/DomainStructureBlock.vue'
import DomainIstLayer from '@/components/domains/DomainIstLayer.vue'
import DomainBefundSlot from '@/components/domains/DomainBefundSlot.vue'
import EmptyState from '@/shared/design/patterns/EmptyState.vue'
import type { Tank } from '@/types'
import { Layers } from 'lucide-vue-next'

interface Props {
  domainKey: string
  domainLabel: string
  expanded: boolean
  devices: StructureDeviceRef[]
  tanks: Tank[]
  zoneIds: string[]
  zoneNames: Record<string, string>
}

defineProps<Props>()

const emit = defineEmits<{
  toggle: []
}>()

const structureRows = ref<DomainStructureRow[]>([])

function onStructureRows(rows: DomainStructureRow[]): void {
  // Replace in place — never clear first (avoids Befund layout jump while n:m loads)
  structureRows.value = rows
}
</script>

<template>
  <section
    class="glass-panel overflow-hidden rounded-lg border border-[var(--glass-border)]"
    :aria-label="`Domäne ${domainLabel}`"
  >
    <button
      type="button"
      class="flex w-full items-center gap-2 px-4 py-3 text-left hover:bg-dark-800/50"
      :aria-expanded="expanded"
      :aria-label="`${domainLabel} ${expanded ? 'zuklappen' : 'aufklappen'}`"
      @click="emit('toggle')"
    >
      <ChevronDown v-if="expanded" class="h-4 w-4 text-dark-300" aria-hidden="true" />
      <ChevronRight v-else class="h-4 w-4 text-dark-300" aria-hidden="true" />
      <span class="text-base font-semibold text-dark-50">{{ domainLabel }}</span>
      <span class="ml-auto text-xs text-dark-400">
        {{ devices.length }} {{ devices.length === 1 ? 'Gerät' : 'Geräte' }}
      </span>
    </button>

    <div v-if="expanded" class="space-y-6 border-t border-dark-700 px-4 py-4">
      <EmptyState
        v-if="devices.length === 0"
        :icon="Layers"
        :title="`Keine Geräte in ${domainLabel}`"
        description="Neutraler Leerzustand — keine fehlende Zuordnung. Domäne am Gerät in den Einstellungen setzen, falls gewünscht."
        cta-text="Zu den Geräten"
        :cta-to="{ name: 'hardware' }"
      />

      <template v-else>
        <!-- Block 1: Struktur -->
        <DomainStructureBlock
          :domain-key="domainKey"
          :devices="devices"
          :tanks="tanks"
          :zone-names="zoneNames"
          @rows="onStructureRows"
        />

        <!-- Block 2: Ist (lazy on expand) -->
        <DomainIstLayer
          :domain-key="domainKey"
          :zone-ids="zoneIds"
          :zone-names="zoneNames"
          :active="expanded"
        />

        <!-- Block 3: Befund-Slot (v1 leer, Kontext-Key = Domäne × Ort × Messgröße) -->
        <section class="space-y-2" aria-label="Befund">
          <h4 class="text-xs font-semibold uppercase tracking-wide text-dark-300">
            Befund
          </h4>
          <DomainBefundSlot
            v-for="row in structureRows"
            :key="`befund-${row.key}`"
            :domain-label="domainLabel"
            :place-label="`${row.zoneLabel} · ${row.placeLabel}`"
            :measure-label="row.measureLabel"
          />
          <DomainBefundSlot
            v-if="structureRows.length === 0"
            :domain-label="domainLabel"
            place-label="Ort ohne Namen"
            measure-label="Messgröße"
          />
        </section>
      </template>
    </div>
  </section>
</template>
