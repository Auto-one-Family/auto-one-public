<script setup lang="ts">
import { computed } from 'vue'
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from 'lucide-vue-next'

const props = defineProps<{
  page: number
  totalPages: number
  totalCount: number
  pageSize: number
}>()

const emit = defineEmits<{
  pageChange: [page: number]
  pageSizeChange: [size: number]
}>()

const pageSizeOptions = [25, 50, 100, 200, 500]

// Calculate visible page numbers
const visiblePages = computed(() => {
  const pages: (number | string)[] = []
  const total = props.totalPages
  const current = props.page
  
  if (total <= 7) {
    // Show all pages if 7 or fewer
    for (let i = 1; i <= total; i++) {
      pages.push(i)
    }
  } else {
    // Always show first page
    pages.push(1)
    
    if (current > 3) {
      pages.push('...')
    }
    
    // Show pages around current
    const start = Math.max(2, current - 1)
    const end = Math.min(total - 1, current + 1)
    
    for (let i = start; i <= end; i++) {
      pages.push(i)
    }
    
    if (current < total - 2) {
      pages.push('...')
    }
    
    // Always show last page
    if (total > 1) {
      pages.push(total)
    }
  }
  
  return pages
})

// Display range
const rangeStart = computed(() => {
  if (props.totalCount === 0) return 0
  return (props.page - 1) * props.pageSize + 1
})

const rangeEnd = computed(() => {
  return Math.min(props.page * props.pageSize, props.totalCount)
})

function goToPage(page: number): void {
  if (page >= 1 && page <= props.totalPages && page !== props.page) {
    emit('pageChange', page)
  }
}
</script>

<template>
  <div class="flex flex-col sm:flex-row items-center justify-between gap-4 py-3">
    <!-- Results info -->
    <div class="text-sm text-dark-400">
      <span v-if="totalCount > 0">
        Showing <span class="text-dark-200">{{ rangeStart }}</span> to 
        <span class="text-dark-200">{{ rangeEnd }}</span> of 
        <span class="text-dark-200">{{ totalCount.toLocaleString() }}</span> results
      </span>
      <span v-else>No results</span>
    </div>
    
    <!-- Page size selector -->
    <div class="flex items-center gap-2">
      <label class="text-sm text-dark-400">Per page:</label>
      <select
        :value="pageSize"
        class="input text-sm py-1 px-2 w-20"
        @change="emit('pageSizeChange', Number(($event.target as HTMLSelectElement).value))"
      >
        <option v-for="size in pageSizeOptions" :key="size" :value="size">
          {{ size }}
        </option>
      </select>
    </div>
    
    <!-- Pagination controls -->
    <div class="flex items-center gap-1">
      <!-- First page -->
      <button
        :disabled="page <= 1"
        class="p-1.5 rounded hover:bg-dark-800 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
        title="First page"
        @click="goToPage(1)"
      >
        <ChevronsLeft class="w-4 h-4" />
      </button>
      
      <!-- Previous page -->
      <button
        :disabled="page <= 1"
        class="p-1.5 rounded hover:bg-dark-800 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
        title="Previous page"
        @click="goToPage(page - 1)"
      >
        <ChevronLeft class="w-4 h-4" />
      </button>
      
      <!-- Page numbers -->
      <div class="flex items-center gap-1 mx-2">
        <template v-for="(p, index) in visiblePages" :key="index">
          <span v-if="p === '...'" class="px-2 text-dark-500">...</span>
          <button
            v-else
            :class="[
              'w-8 h-8 text-sm rounded transition-colors',
              p === page
                ? 'bg-purple-600 text-white'
                : 'hover:bg-dark-800 text-dark-300'
            ]"
            @click="goToPage(p as number)"
          >
            {{ p }}
          </button>
        </template>
      </div>
      
      <!-- Next page -->
      <button
        :disabled="page >= totalPages"
        class="p-1.5 rounded hover:bg-dark-800 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
        title="Next page"
        @click="goToPage(page + 1)"
      >
        <ChevronRight class="w-4 h-4" />
      </button>
      
      <!-- Last page -->
      <button
        :disabled="page >= totalPages"
        class="p-1.5 rounded hover:bg-dark-800 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
        title="Last page"
        @click="goToPage(totalPages)"
      >
        <ChevronsRight class="w-4 h-4" />
      </button>
    </div>
  </div>
</template>





















