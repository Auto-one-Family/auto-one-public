<script setup lang="ts">
/**
 * HierarchyTab — Kaiser → Zone → Subzone → Device tree view.
 *
 * Fetches the full hierarchy from GET /v1/kaiser/god/hierarchy
 * and renders it as a collapsible tree.
 */

import { ref, onMounted } from 'vue'
import {
  Crown, FolderOpen, Layers, Cpu, ChevronDown, ChevronRight,
  RefreshCw, AlertCircle, Wifi, WifiOff, Thermometer, Zap,
} from 'lucide-vue-next'
import api from '@/api/index'
import BaseSkeleton from '@/shared/design/primitives/BaseSkeleton.vue'

interface HierarchyDevice {
  device_id: string
  name: string | null
  status: string
  hardware_type: string
  is_zone_master?: boolean
}

interface HierarchySensor {
  id: string
  gpio: number | null
  sensor_type: string
  sensor_name: string
  esp_id: string
}

interface HierarchyActuator {
  id: string
  gpio: number
  actuator_type: string
  actuator_name: string
  esp_id: string
}

interface HierarchySubzone {
  subzone_id: string
  subzone_name: string | null
  assigned_gpios: number[]
  safe_mode_active: boolean
  custom_data: Record<string, unknown>
  devices: HierarchyDevice[]
  sensors?: HierarchySensor[]
  actuators?: HierarchyActuator[]
}

interface HierarchyZone {
  zone_id: string
  zone_name: string | null
  context: {
    variety: string | null
    growth_phase: string | null
    plant_count: number | null
    substrate: string | null
  } | null
  subzones: HierarchySubzone[]
  devices: HierarchyDevice[]
}

interface HierarchyData {
  kaiser_id: string
  status: string
  total_devices: number
  total_zones: number
  zones: HierarchyZone[]
  unassigned_devices: HierarchyDevice[]
}

const isLoading = ref(true)
const error = ref<string | null>(null)
const data = ref<HierarchyData | null>(null)
const expandedZones = ref<Set<string>>(new Set())
const expandedSubzones = ref<Set<string>>(new Set())

function toggleZone(zoneId: string) {
  if (expandedZones.value.has(zoneId)) {
    expandedZones.value.delete(zoneId)
  } else {
    expandedZones.value.add(zoneId)
  }
}

function toggleSubzone(key: string) {
  if (expandedSubzones.value.has(key)) {
    expandedSubzones.value.delete(key)
  } else {
    expandedSubzones.value.add(key)
  }
}

async function fetchHierarchy() {
  isLoading.value = true
  error.value = null
  try {
    const response = await api.get<{ success: boolean } & HierarchyData>('/kaiser/god/hierarchy')
    data.value = response.data as HierarchyData
    // Auto-expand all zones on first load
    for (const z of data.value.zones) {
      expandedZones.value.add(z.zone_id)
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Hierarchie konnte nicht geladen werden'
  } finally {
    isLoading.value = false
  }
}

function statusColor(status: string): string {
  if (status === 'online') return 'var(--color-success)'
  if (status === 'offline') return 'var(--color-text-muted)'
  if (status === 'error') return 'var(--color-error)'
  return 'var(--color-text-muted)'
}

onMounted(fetchHierarchy)
</script>

<template>
  <div class="hierarchy-tab">
    <div class="hierarchy-tab__header">
      <h3 class="text-base font-semibold text-[var(--color-text-primary)]">
        System-Hierarchie
      </h3>
      <button
        class="hierarchy-tab__refresh"
        :disabled="isLoading"
        title="Aktualisieren"
        @click="fetchHierarchy"
      >
        <RefreshCw :size="14" :class="{ 'animate-spin': isLoading }" />
      </button>
    </div>

    <BaseSkeleton v-if="isLoading" :lines="8" />

    <div v-else-if="error" class="hierarchy-tab__error">
      <AlertCircle :size="16" />
      {{ error }}
    </div>

    <div v-else-if="data" class="hierarchy-tree">
      <!-- Kaiser Root -->
      <div class="tree-node tree-node--kaiser">
        <Crown :size="16" class="text-[var(--color-warning)]" />
        <span class="tree-node__label font-semibold">
          Kaiser: {{ data.kaiser_id }}
        </span>
        <span class="tree-node__badge">
          {{ data.total_zones }} Zonen · {{ data.total_devices }} Geräte
        </span>
      </div>

      <!-- Zones -->
      <div
        v-for="zone in data.zones"
        :key="zone.zone_id"
        class="tree-branch"
      >
        <div class="tree-node tree-node--zone" @click="toggleZone(zone.zone_id)">
          <component
            :is="expandedZones.has(zone.zone_id) ? ChevronDown : ChevronRight"
            :size="14"
            class="tree-node__chevron"
          />
          <FolderOpen :size="14" class="text-[var(--color-iridescent-1)]" />
          <span class="tree-node__label">
            {{ zone.zone_name || zone.zone_id }}
          </span>
          <span v-if="zone.context?.growth_phase" class="tree-node__phase">
            {{ zone.context.growth_phase.replace(/_/g, ' ') }}
          </span>
          <span v-if="zone.context?.variety" class="tree-node__variety">
            {{ zone.context.variety }}
          </span>
          <span class="tree-node__count">
            {{ zone.devices.length + zone.subzones.reduce((a, s) => a + s.devices.length, 0) }} ESP
          </span>
        </div>

        <div v-if="expandedZones.has(zone.zone_id)" class="tree-children">
          <!-- Subzones -->
          <div
            v-for="sz in zone.subzones"
            :key="sz.subzone_id"
            class="tree-branch"
          >
            <div
              class="tree-node tree-node--subzone"
              @click="toggleSubzone(`${zone.zone_id}/${sz.subzone_id}`)"
            >
              <component
                :is="expandedSubzones.has(`${zone.zone_id}/${sz.subzone_id}`) ? ChevronDown : ChevronRight"
                :size="12"
                class="tree-node__chevron"
              />
              <Layers :size="12" class="text-[var(--color-iridescent-3)]" />
              <span class="tree-node__label text-sm">
                {{ sz.subzone_name || sz.subzone_id }}
              </span>
              <span class="tree-node__badge text-xs">
                GPIO {{ sz.assigned_gpios.join(', ') }}
              </span>
              <span v-if="sz.safe_mode_active" class="tree-node__safe">Safe</span>
            </div>

            <div
              v-if="expandedSubzones.has(`${zone.zone_id}/${sz.subzone_id}`)"
              class="tree-children"
            >
              <!-- B2: Sensoren und Aktoren pro Subzone (statt nur ESPs) -->
              <div
                v-for="s in (sz.sensors ?? [])"
                :key="'s-' + s.id"
                class="tree-node tree-node--sensor"
              >
                <Thermometer :size="12" class="text-[var(--color-iridescent-1)]" />
                <span class="tree-node__label text-sm">{{ s.sensor_name || s.sensor_type }}</span>
                <span class="tree-node__badge text-xs">GPIO {{ s.gpio ?? '?' }} · {{ s.esp_id }}</span>
              </div>
              <div
                v-for="a in (sz.actuators ?? [])"
                :key="'a-' + a.id"
                class="tree-node tree-node--actuator"
              >
                <Zap :size="12" class="text-[var(--color-warning)]" />
                <span class="tree-node__label text-sm">{{ a.actuator_name || a.actuator_type }}</span>
                <span class="tree-node__badge text-xs">GPIO {{ a.gpio }} · {{ a.esp_id }}</span>
              </div>
              <!-- ESPs als Fallback wenn keine Sensoren/Aktoren -->
              <div
                v-if="!(sz.sensors?.length || sz.actuators?.length) && sz.devices?.length"
                v-for="dev in sz.devices"
                :key="dev.device_id"
                class="tree-node tree-node--device"
              >
                <Cpu :size="12" />
                <component :is="dev.status === 'online' ? Wifi : WifiOff" :size="10" :style="{ color: statusColor(dev.status) }" />
                <span class="tree-node__label text-sm">{{ dev.name || dev.device_id }}</span>
                <span class="tree-node__device-id">{{ dev.device_id }}</span>
              </div>
            </div>
          </div>

          <!-- Zone-level devices (no subzone) -->
          <div
            v-for="dev in zone.devices"
            :key="dev.device_id"
            class="tree-node tree-node--device"
          >
            <Cpu :size="12" />
            <component :is="dev.status === 'online' ? Wifi : WifiOff" :size="10" :style="{ color: statusColor(dev.status) }" />
            <span class="tree-node__label text-sm">{{ dev.name || dev.device_id }}</span>
            <span class="tree-node__device-id">{{ dev.device_id }}</span>
          </div>
        </div>
      </div>

      <!-- Unassigned -->
      <div v-if="data.unassigned_devices.length > 0" class="tree-branch">
        <div class="tree-node tree-node--unassigned">
          <AlertCircle :size="14" class="text-[var(--color-warning)]" />
          <span class="tree-node__label">Nicht zugewiesen</span>
          <span class="tree-node__count">{{ data.unassigned_devices.length }}</span>
        </div>
        <div class="tree-children">
          <div
            v-for="dev in data.unassigned_devices"
            :key="dev.device_id"
            class="tree-node tree-node--device"
          >
            <Cpu :size="12" />
            <span class="tree-node__label text-sm">{{ dev.name || dev.device_id }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.hierarchy-tab {
  padding: var(--space-4);
}

.hierarchy-tab__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-4);
}

.hierarchy-tab__refresh {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: var(--radius-sm);
  background: var(--color-bg-tertiary);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.hierarchy-tab__refresh:hover {
  color: var(--color-text-primary);
  border-color: var(--color-iridescent-1);
}

.hierarchy-tab__error {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  color: var(--color-error);
  font-size: var(--text-sm);
}

.hierarchy-tree {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.tree-branch {
  margin-left: var(--space-4);
}

.tree-node {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
  transition: background var(--transition-fast);
}

.tree-node--kaiser {
  margin-left: 0;
  padding: var(--space-2) var(--space-3);
  background: rgba(251, 191, 36, 0.08);
  border: 1px solid rgba(251, 191, 36, 0.15);
  border-radius: var(--radius-sm);
  margin-bottom: var(--space-2);
}

.tree-node--zone {
  cursor: pointer;
}

.tree-node--zone:hover {
  background: rgba(255, 255, 255, 0.04);
}

.tree-node--subzone {
  cursor: pointer;
}

.tree-node--subzone:hover {
  background: rgba(255, 255, 255, 0.03);
}

.tree-node__chevron {
  color: var(--color-text-muted);
  flex-shrink: 0;
}

.tree-node__label {
  color: var(--color-text-primary);
  font-size: var(--text-sm);
}

.tree-node__badge {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.tree-node__phase {
  font-size: var(--text-xs);
  color: var(--color-iridescent-3);
  background: rgba(167, 139, 250, 0.1);
  padding: 0 var(--space-1);
  border-radius: var(--radius-xs);
  text-transform: capitalize;
}

.tree-node__variety {
  font-size: var(--text-xs);
  color: var(--color-success);
  font-style: italic;
}

.tree-node__count {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  margin-left: auto;
}

.tree-node__safe {
  font-size: var(--text-xxs);
  color: var(--color-warning);
  background: rgba(251, 191, 36, 0.1);
  padding: 0 4px;
  border-radius: var(--radius-xs);
}

.tree-node__device-id {
  font-size: var(--text-xxs);
  color: var(--color-text-muted);
  font-family: var(--font-mono);
}

.tree-node--device {
  padding-left: var(--space-4);
}

.tree-children {
  display: flex;
  flex-direction: column;
  gap: 1px;
  border-left: 1px solid rgba(255, 255, 255, 0.06);
  margin-left: var(--space-2);
  padding-left: var(--space-2);
}

.tree-node--unassigned {
  opacity: 0.7;
}
</style>
