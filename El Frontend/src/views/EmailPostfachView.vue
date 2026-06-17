<script setup lang="ts">
/**
 * EmailPostfachView — E-Mail-Postfach (Admin)
 *
 * Vollständige Übersicht aller systemrelevanten E-Mails mit Filter, Pagination
 * und Detail-Panel. Nutzt Email-Log-API.
 */

import { onMounted } from 'vue'
import { useEmailPostfach } from '@/composables/useEmailPostfach'
import { formatDateTime } from '@/utils/formatters'
import { getEmailStatusLabel } from '@/utils/labels'
import SlideOver from '@/shared/design/primitives/SlideOver.vue'
import BaseSelect from '@/shared/design/primitives/BaseSelect.vue'
import BaseInput from '@/shared/design/primitives/BaseInput.vue'
import BaseButton from '@/shared/design/primitives/BaseButton.vue'
import ErrorState from '@/shared/design/patterns/ErrorState.vue'
import EmptyState from '@/shared/design/patterns/EmptyState.vue'
import BaseSkeleton from '@/shared/design/primitives/BaseSkeleton.vue'
import Pagination from '@/components/database/Pagination.vue'
import { Mail, MailX, ExternalLink, RotateCcw } from 'lucide-vue-next'

const {
  emails,
  stats,
  isLoading,
  error,
  pagination,
  selectedEntry,
  lastLoadedAt,
  statusFilter,
  dateFrom,
  dateTo,
  templateFilter,
  pageSize,
  loadEmails,
  loadStats,
  openDetail,
  closeDetail,
  goToPage,
  setPageSize,
  resetFilters,
} = useEmailPostfach()

const STATUS_OPTIONS = [
  { value: '', label: 'Alle Status' },
  { value: 'sent', label: 'Zugestellt' },
  { value: 'failed', label: 'Fehlgeschlagen' },
  { value: 'pending', label: 'Ausstehend' },
  { value: 'permanently_failed', label: 'Dauerhaft fehlgeschlagen' },
]

onMounted(() => {
  loadEmails()
  loadStats()
})
</script>

<template>
  <div class="postfach">
    <header class="postfach__header">
      <h1 class="postfach__title">
        <Mail class="postfach__title-icon" />
        E-Mail-Postfach
      </h1>
      <p class="postfach__subtitle">
        Systemrelevante E-Mails: Alerts, Digest, Test-Emails
      </p>
      <p v-if="lastLoadedAt" class="postfach__subtitle">
        Datenstand: {{ formatDateTime(lastLoadedAt) }}
      </p>
    </header>

    <!-- Filter Bar -->
    <div class="postfach__filter-bar">
      <div class="postfach__filter-row">
        <BaseSelect
          v-model="statusFilter"
          :options="STATUS_OPTIONS"
          label="Status"
          class="postfach__filter-status"
        />
        <div class="postfach__filter-date">
          <label class="postfach__filter-label">Von</label>
          <input
            v-model="dateFrom"
            type="date"
            lang="de"
            placeholder="TT.MM.JJJJ"
            class="postfach__filter-input"
          />
        </div>
        <div class="postfach__filter-date">
          <label class="postfach__filter-label">Bis</label>
          <input
            v-model="dateTo"
            type="date"
            lang="de"
            placeholder="TT.MM.JJJJ"
            class="postfach__filter-input"
          />
        </div>
        <BaseInput
          v-model="templateFilter"
          type="text"
          label="Template"
          placeholder="Teilstring suchen"
          class="postfach__filter-template"
        />
        <BaseButton
          variant="ghost"
          size="sm"
          class="postfach__filter-reset"
          @click="resetFilters"
        >
          <RotateCcw class="w-4 h-4" />
          Zurücksetzen
        </BaseButton>
      </div>
    </div>

    <!-- Stats (P1) -->
    <div v-if="stats && stats.total > 0" class="postfach__stats">
      <span class="postfach__stat">
        <span class="postfach__stat-value">{{ stats.total }}</span> gesamt
      </span>
      <span class="postfach__stat postfach__stat--sent">
        <span class="postfach__stat-value">{{ stats.sent }}</span> zugestellt
      </span>
      <span class="postfach__stat postfach__stat--failed">
        <span class="postfach__stat-value">{{ stats.failed }}</span> fehlgeschlagen
      </span>
    </div>

    <!-- Content -->
    <div class="postfach__content card overflow-hidden">
      <BaseSkeleton
        v-if="isLoading && emails.length === 0"
        text="Lade E-Mail-Log..."
        full-height
      />
      <ErrorState
        v-else-if="error"
        :message="error"
        @retry="loadEmails"
      />
      <template v-else>
        <div class="postfach__table-wrapper">
          <table class="postfach__table">
            <thead>
              <tr class="postfach__thead-row">
                <th class="postfach__th">Datum</th>
                <th class="postfach__th">Betreff</th>
                <th class="postfach__th">An</th>
                <th class="postfach__th">Status</th>
                <th class="postfach__th">Template</th>
                <th class="postfach__th">Retry</th>
                <th class="postfach__th postfach__th--actions">Aktionen</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="entry in emails"
                :key="entry.id"
                class="postfach__row"
                @click="openDetail(entry)"
              >
                <td class="postfach__cell postfach__cell--date">
                  {{ formatDateTime(entry.sent_at || entry.created_at) }}
                </td>
                <td class="postfach__cell postfach__cell--subject">
                  {{ entry.subject }}
                </td>
                <td class="postfach__cell postfach__cell--to">
                  {{ entry.to_address }}
                </td>
                <td class="postfach__cell postfach__cell--status">
                  <span
                    :class="['postfach__dot', `postfach__dot--${entry.status}`]"
                  />
                  {{ getEmailStatusLabel(entry.status) }}
                </td>
                <td class="postfach__cell postfach__cell--template">
                  {{ entry.template || '-' }}
                </td>
                <td class="postfach__cell postfach__cell--retry">
                  <span
                    v-if="(entry.status === 'failed' || entry.status === 'permanently_failed') && entry.retry_count > 0"
                    class="postfach__retry"
                  >
                    {{ entry.retry_count }}/3
                  </span>
                  <span v-else>-</span>
                </td>
                <td class="postfach__cell postfach__cell--actions">
                  <button
                    class="postfach__detail-btn"
                    title="Details"
                    @click.stop="openDetail(entry)"
                  >
                    Details
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <EmptyState
          v-if="emails.length === 0 && !isLoading"
          :icon="MailX"
          title="Keine E-Mails gefunden"
          :description="(statusFilter || dateFrom || dateTo || templateFilter)
            ? 'Mit den aktuellen Filterkriterien wurden keine E-Mails gefunden. Setze die Filter zurück, um alle Eintraege zu sehen.'
            : 'Sobald das System E-Mails versendet (Alerts, Tagesberichte, Test-Mails), erscheinen sie hier mit Status, Empfaenger und Template.'"
          :action-text="(statusFilter || dateFrom || dateTo || templateFilter) ? 'Filter zuruecksetzen' : undefined"
          @action="resetFilters"
        />


        <Pagination
          v-if="pagination && pagination.total_items > 0"
          :page="pagination.page"
          :total-pages="pagination.total_pages"
          :total-count="pagination.total_items"
          :page-size="pageSize"
          @page-change="goToPage"
          @page-size-change="setPageSize"
        />
      </template>
    </div>

    <!-- Detail SlideOver -->
    <SlideOver
      :open="!!selectedEntry"
      title="E-Mail-Details"
      width="md"
      @close="closeDetail"
    >
      <template v-if="selectedEntry">
        <dl class="postfach__detail-dl">
          <dt class="postfach__detail-dt">Betreff</dt>
          <dd class="postfach__detail-dd">{{ selectedEntry.subject }}</dd>

          <dt class="postfach__detail-dt">An</dt>
          <dd class="postfach__detail-dd">{{ selectedEntry.to_address }}</dd>

          <dt class="postfach__detail-dt">Status</dt>
          <dd class="postfach__detail-dd">
            <span
              :class="['postfach__dot', `postfach__dot--${selectedEntry.status}`]"
            />
            {{ getEmailStatusLabel(selectedEntry.status) }}
          </dd>

          <dt class="postfach__detail-dt">Template</dt>
          <dd class="postfach__detail-dd">{{ selectedEntry.template || '-' }}</dd>

          <dt class="postfach__detail-dt">Provider</dt>
          <dd class="postfach__detail-dd">{{ selectedEntry.provider }}</dd>

          <dt
            v-if="(selectedEntry.status === 'failed' || selectedEntry.status === 'permanently_failed') && selectedEntry.retry_count > 0"
            class="postfach__detail-dt"
          >
            Versuche
          </dt>
          <dd
            v-if="(selectedEntry.status === 'failed' || selectedEntry.status === 'permanently_failed') && selectedEntry.retry_count > 0"
            class="postfach__detail-dd"
          >
            {{ selectedEntry.retry_count }}/3
          </dd>

          <dt
            v-if="selectedEntry.error_message"
            class="postfach__detail-dt"
          >
            Fehler
          </dt>
          <dd
            v-if="selectedEntry.error_message"
            class="postfach__detail-dd postfach__detail-dd--error"
          >
            {{ selectedEntry.error_message }}
          </dd>

          <dt class="postfach__detail-dt">Gesendet</dt>
          <dd class="postfach__detail-dd">
            {{ formatDateTime(selectedEntry.sent_at) }}
          </dd>

          <dt class="postfach__detail-dt">Erstellt</dt>
          <dd class="postfach__detail-dd">
            {{ formatDateTime(selectedEntry.created_at) }}
          </dd>

          <dt
            v-if="selectedEntry.notification_id"
            class="postfach__detail-dt"
          >
            Verknüpfte Notification
          </dt>
          <dd
            v-if="selectedEntry.notification_id"
            class="postfach__detail-dd"
          >
            <RouterLink
              :to="{
                path: '/system-monitor',
                query: {
                  tab: 'events',
                  correlation: selectedEntry.notification_id,
                },
              }"
              class="postfach__detail-link"
              @click="closeDetail"
            >
              <ExternalLink class="w-4 h-4" />
              Ereignisse anzeigen
            </RouterLink>
          </dd>
        </dl>
      </template>
    </SlideOver>
  </div>
</template>

<style scoped>
.postfach {
  padding: var(--space-4);
  max-width: 1400px;
  margin: 0 auto;
}

.postfach__header {
  margin-bottom: var(--space-4);
}

.postfach__title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-xl);
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0 0 var(--space-1) 0;
}

.postfach__title-icon {
  width: 24px;
  height: 24px;
  color: var(--color-iridescent-2);
}

.postfach__subtitle {
  font-size: var(--text-sm);
  color: var(--color-text-muted);
  margin: 0;
}

.postfach__filter-bar {
  margin-bottom: var(--space-4);
}

.postfach__filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  align-items: flex-end;
}

.postfach__filter-status {
  min-width: 180px;
}

.postfach__filter-date {
  min-width: 140px;
}

.postfach__filter-label {
  display: block;
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-text-secondary);
  margin-bottom: var(--space-1);
}

.postfach__filter-input {
  width: 100%;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  color: var(--color-text-primary);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  transition: border-color var(--transition-fast);
}

.postfach__filter-input:focus {
  outline: none;
  border-color: var(--color-accent);
  box-shadow: 0 0 0 2px var(--color-accent-dim);
}

.postfach__filter-template {
  min-width: 160px;
}

.postfach__filter-reset {
  margin-left: auto;
}

.postfach__stats {
  display: flex;
  gap: var(--space-4);
  margin-bottom: var(--space-4);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.postfach__stat-value {
  font-weight: 600;
  color: var(--color-text-primary);
}

.postfach__stat--sent .postfach__stat-value {
  color: var(--color-success);
}

.postfach__stat--failed .postfach__stat-value {
  color: var(--color-error);
}

.postfach__content {
  background: var(--color-bg-secondary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
}

.postfach__table-wrapper {
  overflow-x: auto;
}

.postfach__table {
  width: 100%;
  border-collapse: collapse;
}

.postfach__thead-row {
  border-bottom: 1px solid var(--glass-border);
}

.postfach__th {
  padding: var(--space-3) var(--space-4);
  text-align: left;
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
}

.postfach__th--actions {
  text-align: right;
}

.postfach__row {
  border-bottom: 1px solid var(--glass-border);
  cursor: pointer;
  transition: background-color var(--transition-fast);
}

.postfach__row:hover {
  background-color: rgba(255, 255, 255, 0.03);
}

.postfach__cell {
  padding: var(--space-3) var(--space-4);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.postfach__cell--date {
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

.postfach__cell--subject {
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.postfach__cell--to {
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.postfach__cell--status {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.postfach__cell--actions {
  text-align: right;
}

.postfach__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.postfach__dot--sent {
  background: var(--color-success);
}

.postfach__dot--failed {
  background: var(--color-error);
}

.postfach__dot--pending {
  background: var(--color-text-muted);
}

.postfach__dot--permanently_failed {
  background: var(--color-error);
}

.postfach__retry {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.postfach__detail-btn {
  padding: var(--space-1) var(--space-2);
  font-size: var(--text-xs);
  color: var(--color-iridescent-2);
  background: transparent;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.postfach__detail-btn:hover {
  background: rgba(129, 140, 248, 0.1);
}

.postfach__empty {
  padding: var(--space-8);
  text-align: center;
  color: var(--color-text-muted);
}

.postfach__detail-dl {
  display: grid;
  gap: var(--space-3);
}

.postfach__detail-dt {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-secondary);
  text-transform: uppercase;
}

.postfach__detail-dd {
  font-size: var(--text-sm);
  color: var(--color-text-primary);
  margin: 0;
}

.postfach__detail-dd--error {
  color: var(--color-error);
  word-break: break-word;
}

.postfach__detail-link {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  color: var(--color-iridescent-2);
  text-decoration: none;
  font-size: var(--text-sm);
}

.postfach__detail-link:hover {
  text-decoration: underline;
}
</style>
