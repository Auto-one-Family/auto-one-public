<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { usersApi, type User, type UserCreate, type UserUpdate, type UserRole } from '@/api/users'
import { formatUiApiError, toUiApiError } from '@/api/uiApiError'
import { useAuthStore } from '@/shared/stores/auth.store'
import {
  Plus, Edit, Trash2, Key, RefreshCw, AlertCircle, Check, X,
  Shield, Eye, Settings, UserCheck, UserX
} from 'lucide-vue-next'
import BaseModal from '@/shared/design/primitives/BaseModal.vue'
import BaseButton from '@/shared/design/primitives/BaseButton.vue'

const authStore = useAuthStore()
const router = useRouter()

// State
const users = ref<User[]>([])
const isLoading = ref(false)
const error = ref<string | null>(null)
const successMessage = ref<string | null>(null)

// Modals
const showCreateModal = ref(false)
const showEditModal = ref(false)
const showDeleteModal = ref(false)
const showResetPasswordModal = ref(false)
const showChangePasswordModal = ref(false)

// Selected user for edit/delete
const selectedUser = ref<User | null>(null)

// Form data
const createForm = ref<UserCreate>({
  username: '',
  email: '',
  password: '',
  full_name: '',
  role: 'viewer'
})

const editForm = ref<UserUpdate>({})

const newPassword = ref('')
const currentPassword = ref('')
const confirmPassword = ref('')

let successTimeout: ReturnType<typeof setTimeout> | null = null

// Helper function to manage success message timeout
function clearSuccessAfterDelay() {
  if (successTimeout) clearTimeout(successTimeout)
  successTimeout = setTimeout(() => { successMessage.value = null }, 3000)
}

// Role options
// B7.1: Admin-Badge nutzt accent (NICHT error/red), damit Rolle != Alarm signalisiert wird.
const ROLES: { value: UserRole; label: string; icon: typeof Shield; color: string }[] = [
  { value: 'admin', label: 'Admin', icon: Shield, color: 'role-badge--admin' },
  { value: 'operator', label: 'Operator', icon: Settings, color: 'role-badge--operator' },
  { value: 'viewer', label: 'Viewer', icon: Eye, color: 'role-badge--viewer' }
]

// Methods
async function loadUsers(): Promise<void> {
  isLoading.value = true
  error.value = null

  try {
    users.value = await usersApi.listUsers()
  } catch (err: unknown) {
    error.value = formatUiApiError(toUiApiError(err, 'Benutzer konnten nicht geladen werden'))
  } finally {
    isLoading.value = false
  }
}

function openCreateModal(): void {
  createForm.value = {
    username: '',
    email: '',
    password: '',
    full_name: '',
    role: 'viewer'
  }
  showCreateModal.value = true
}

async function createUser(): Promise<void> {
  isLoading.value = true
  error.value = null

  try {
    await usersApi.createUser(createForm.value)
    showCreateModal.value = false
    successMessage.value = 'User created successfully'
    await loadUsers()
    clearSuccessAfterDelay()
  } catch (err: unknown) {
    error.value = formatUiApiError(toUiApiError(err, 'Benutzer konnte nicht erstellt werden'))
  } finally {
    isLoading.value = false
  }
}

function openEditModal(user: User): void {
  selectedUser.value = user
  editForm.value = {
    email: user.email,
    full_name: user.full_name || '',
    role: user.role,
    is_active: user.is_active
  }
  showEditModal.value = true
}

async function updateUser(): Promise<void> {
  if (!selectedUser.value) return

  isLoading.value = true
  error.value = null

  try {
    await usersApi.updateUser(selectedUser.value.id, editForm.value)
    showEditModal.value = false
    successMessage.value = 'User updated successfully'
    await loadUsers()
    clearSuccessAfterDelay()
  } catch (err: unknown) {
    error.value = formatUiApiError(toUiApiError(err, 'Benutzer konnte nicht aktualisiert werden'))
  } finally {
    isLoading.value = false
  }
}

function openDeleteModal(user: User): void {
  selectedUser.value = user
  showDeleteModal.value = true
}

async function deleteUser(): Promise<void> {
  if (!selectedUser.value) return

  isLoading.value = true
  error.value = null

  try {
    await usersApi.deleteUser(selectedUser.value.id)
    showDeleteModal.value = false
    successMessage.value = 'User deleted successfully'
    await loadUsers()
    clearSuccessAfterDelay()
  } catch (err: unknown) {
    error.value = formatUiApiError(toUiApiError(err, 'Benutzer konnte nicht gelöscht werden'))
  } finally {
    isLoading.value = false
  }
}

function openResetPasswordModal(user: User): void {
  selectedUser.value = user
  newPassword.value = ''
  confirmPassword.value = ''
  showResetPasswordModal.value = true
}

async function resetPassword(): Promise<void> {
  if (!selectedUser.value) return

  if (newPassword.value !== confirmPassword.value) {
    error.value = 'Passwords do not match'
    return
  }

  isLoading.value = true
  error.value = null

  try {
    await usersApi.resetPassword(selectedUser.value.id, newPassword.value)
    showResetPasswordModal.value = false
    successMessage.value = 'Password reset successfully'
    clearSuccessAfterDelay()
  } catch (err: unknown) {
    error.value = formatUiApiError(toUiApiError(err, 'Passwort konnte nicht zurückgesetzt werden'))
  } finally {
    isLoading.value = false
  }
}

function openChangePasswordModal(): void {
  currentPassword.value = ''
  newPassword.value = ''
  confirmPassword.value = ''
  showChangePasswordModal.value = true
}

async function changeOwnPassword(): Promise<void> {
  if (newPassword.value !== confirmPassword.value) {
    error.value = 'Passwords do not match'
    return
  }

  isLoading.value = true
  error.value = null

  try {
    await usersApi.changeOwnPassword(currentPassword.value, newPassword.value)
    showChangePasswordModal.value = false
    successMessage.value = 'Password changed successfully'
    clearSuccessAfterDelay()
  } catch (err: unknown) {
    error.value = formatUiApiError(toUiApiError(err, 'Passwort konnte nicht geändert werden'))
  } finally {
    isLoading.value = false
  }
}

function getRoleConfig(role: string) {
  return ROLES.find(r => r.value === role) || ROLES[2]
}

function formatDate(dateStr: string): string {
  try {
    return new Intl.DateTimeFormat('de-DE', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    }).format(new Date(dateStr))
  } catch {
    return dateStr
  }
}

const isCurrentUser = computed(() => (user: User) => String(user.id) === String(authStore.user?.id))
const isForbiddenError = computed(() => (error.value ?? '').includes('Zugriff verweigert'))

function goBack(): void {
  router.back()
}

function goHome(): void {
  router.push('/')
}

onMounted(() => {
  loadUsers()
})

onUnmounted(() => {
  if (successTimeout) {
    clearTimeout(successTimeout)
  }
})
</script>

<template>
  <div class="h-full overflow-auto space-y-6">
    <!-- Header Actions -->
    <div class="flex flex-wrap items-center gap-2 justify-end">
        <BaseButton
          variant="secondary"
          data-testid="user-management-change-password-button"
          @click="openChangePasswordModal"
        >
          <Key class="w-4 h-4 mr-2" />
          Change My Password
        </BaseButton>
        <BaseButton
          variant="primary"
          data-testid="user-management-add-user-button"
          @click="openCreateModal"
        >
          <Plus class="w-4 h-4 mr-2" />
          Add User
        </BaseButton>
    </div>

    <!-- Alerts -->
    <div
      v-if="error"
      class="p-4 rounded-lg bg-red-500/10 border border-red-500/30 flex items-start gap-3"
    >
      <AlertCircle class="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
      <div class="flex-1">
        <p class="text-sm text-red-400">{{ error }}</p>
        <div v-if="isForbiddenError" class="mt-3 flex flex-wrap gap-2">
          <button class="btn-secondary text-xs" @click="goBack">Zurück</button>
          <button class="btn-secondary text-xs" @click="goHome">Zur Startansicht</button>
          <button class="btn-secondary text-xs" @click="loadUsers">Erneut versuchen</button>
        </div>
      </div>
      <button class="text-red-400 hover:text-red-300" @click="error = null">
        <X class="w-4 h-4" />
      </button>
    </div>

    <div
      v-if="successMessage"
      class="p-4 rounded-lg bg-green-500/10 border border-green-500/30 flex items-start gap-3"
    >
      <Check class="w-5 h-5 text-green-400 flex-shrink-0 mt-0.5" />
      <p class="text-sm text-green-400">{{ successMessage }}</p>
    </div>

    <!-- Users Table -->
    <div class="card overflow-hidden">
      <table class="w-full">
        <thead>
          <tr class="border-b border-dark-700">
            <th class="p-4 text-left text-xs font-medium text-dark-400 uppercase">User</th>
            <th class="p-4 text-left text-xs font-medium text-dark-400 uppercase">Email</th>
            <th class="p-4 text-left text-xs font-medium text-dark-400 uppercase">Role</th>
            <th class="p-4 text-left text-xs font-medium text-dark-400 uppercase">Status</th>
            <th class="p-4 text-left text-xs font-medium text-dark-400 uppercase">Created</th>
            <th class="p-4 text-right text-xs font-medium text-dark-400 uppercase">Actions</th>
          </tr>
        </thead>
        <tbody v-if="!isLoading && users.length > 0">
          <tr
            v-for="user in users"
            :key="user.id"
            class="border-b border-dark-800 hover:bg-dark-800/50"
          >
            <td class="p-4">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-full bg-dark-700 flex items-center justify-center">
                  <span class="text-sm font-medium text-dark-200">
                    {{ user.username.charAt(0).toUpperCase() }}
                  </span>
                </div>
                <div>
                  <p class="font-medium text-dark-100">
                    {{ user.username }}
                    <span v-if="isCurrentUser(user)" class="text-xs text-purple-400 ml-1">(you)</span>
                  </p>
                  <p v-if="user.full_name" class="text-xs text-dark-400">{{ user.full_name }}</p>
                </div>
              </div>
            </td>
            <td class="p-4 text-sm text-dark-300">{{ user.email }}</td>
            <td class="p-4">
              <span
                :class="[
                  'role-badge inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-medium',
                  getRoleConfig(user.role).color
                ]"
              >
                <component :is="getRoleConfig(user.role).icon" class="w-3 h-3" />
                {{ getRoleConfig(user.role).label }}
              </span>
            </td>
            <td class="p-4">
              <span
                :class="[
                  'inline-flex items-center gap-1 px-2 py-1 rounded text-xs',
                  user.is_active ? 'text-green-400 bg-green-400/10' : 'text-red-400 bg-red-400/10'
                ]"
              >
                <component :is="user.is_active ? UserCheck : UserX" class="w-3 h-3" />
                {{ user.is_active ? 'Active' : 'Inactive' }}
              </span>
            </td>
            <td class="p-4 text-sm text-dark-400">{{ formatDate(user.created_at) }}</td>
            <td class="p-4">
              <div class="flex items-center justify-end gap-3">
                <button
                  class="min-w-[44px] min-h-[44px] p-2 rounded hover:bg-dark-700 text-dark-400 hover:text-dark-200 transition-colors flex items-center justify-center"
                  title="Bearbeiten"
                  aria-label="Benutzer bearbeiten"
                  @click="openEditModal(user)"
                >
                  <Edit class="w-4 h-4" />
                </button>
                <button
                  class="min-w-[44px] min-h-[44px] p-2 rounded hover:bg-dark-700 text-dark-400 hover:text-yellow-400 transition-colors flex items-center justify-center"
                  title="Passwort zurücksetzen"
                  aria-label="Passwort zurücksetzen"
                  @click="openResetPasswordModal(user)"
                >
                  <Key class="w-4 h-4" />
                </button>
                <button
                  v-if="!isCurrentUser(user)"
                  class="min-w-[44px] min-h-[44px] p-2 rounded hover:bg-dark-700 text-dark-400 hover:text-red-400 transition-colors flex items-center justify-center"
                  title="Löschen"
                  aria-label="Benutzer löschen"
                  @click="openDeleteModal(user)"
                >
                  <Trash2 class="w-4 h-4" />
                </button>
              </div>
            </td>
          </tr>
        </tbody>
        <tbody v-else-if="isLoading">
          <tr>
            <td colspan="6" class="p-8 text-center text-dark-400">
              <div class="flex items-center justify-center gap-2">
                <RefreshCw class="w-4 h-4 animate-spin" />
                Loading users...
              </div>
            </td>
          </tr>
        </tbody>
        <tbody v-else>
          <tr>
            <td colspan="6" class="p-8 text-center text-dark-400">
              No users found
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Create User Modal -->
    <BaseModal :open="showCreateModal" @update:open="showCreateModal = $event" title="Create User" max-width="max-w-md">
      <div class="space-y-4">
        <div>
          <label class="label">Username</label>
          <input v-model="createForm.username" type="text" class="input w-full" />
        </div>
        <div>
          <label class="label">Email</label>
          <input v-model="createForm.email" type="email" class="input w-full" />
        </div>
        <div>
          <label class="label">Password</label>
          <input v-model="createForm.password" type="password" class="input w-full" />
          <p class="text-xs text-dark-500 mt-1">Min 8 chars, with uppercase, lowercase, and digit</p>
        </div>
        <div>
          <label class="label">Full Name (optional)</label>
          <input v-model="createForm.full_name" type="text" class="input w-full" />
        </div>
        <div>
          <label class="label">Role</label>
          <select v-model="createForm.role" class="input w-full">
            <option v-for="role in ROLES" :key="role.value" :value="role.value">
              {{ role.label }}
            </option>
          </select>
        </div>
      </div>
      <template #footer>
        <div class="flex justify-end gap-2">
          <BaseButton
            variant="secondary"
            :disabled="isLoading"
            @click="showCreateModal = false"
          >
            Cancel
          </BaseButton>
          <BaseButton
            variant="primary"
            :disabled="isLoading"
            @click="createUser"
          >
            Create User
          </BaseButton>
        </div>
      </template>
    </BaseModal>

    <!-- Edit User Modal -->
    <BaseModal :open="showEditModal && !!selectedUser" @update:open="showEditModal = $event" :title="`Edit User: ${selectedUser?.username ?? ''}`" max-width="max-w-md">
      <div class="space-y-4">
        <div>
          <label class="label">Email</label>
          <input v-model="editForm.email" type="email" class="input w-full" />
        </div>
        <div>
          <label class="label">Full Name</label>
          <input v-model="editForm.full_name" type="text" class="input w-full" />
        </div>
        <div>
          <label class="label">Role</label>
          <select v-model="editForm.role" class="input w-full">
            <option v-for="role in ROLES" :key="role.value" :value="role.value">
              {{ role.label }}
            </option>
          </select>
        </div>
        <div>
          <label class="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" v-model="editForm.is_active" class="rounded" />
            <span class="text-dark-200">Account Active</span>
          </label>
        </div>
      </div>
      <template #footer>
        <div class="flex justify-end gap-2">
          <button class="btn-secondary" @click="showEditModal = false">Cancel</button>
          <button class="btn-primary" :disabled="isLoading" @click="updateUser">
            Save Changes
          </button>
        </div>
      </template>
    </BaseModal>

    <!-- Delete Confirmation Modal -->
    <BaseModal :open="showDeleteModal && !!selectedUser" @update:open="showDeleteModal = $event" title="Delete User" max-width="max-w-md">
      <p class="text-dark-300">
        Are you sure you want to delete user <strong class="text-dark-100">{{ selectedUser?.username }}</strong>?
        This action cannot be undone.
      </p>
      <template #footer>
        <div class="flex justify-end gap-2">
          <button class="btn-secondary" @click="showDeleteModal = false">Cancel</button>
          <button class="btn-danger" :disabled="isLoading" @click="deleteUser">
            Delete User
          </button>
        </div>
      </template>
    </BaseModal>

    <!-- Reset Password Modal -->
    <BaseModal :open="showResetPasswordModal && !!selectedUser" @update:open="showResetPasswordModal = $event" :title="`Reset Password: ${selectedUser?.username ?? ''}`" max-width="max-w-md">
      <div class="space-y-4">
        <div>
          <label class="label">New Password</label>
          <input v-model="newPassword" type="password" class="input w-full" />
        </div>
        <div>
          <label class="label">Confirm Password</label>
          <input v-model="confirmPassword" type="password" class="input w-full" />
        </div>
      </div>
      <template #footer>
        <div class="flex justify-end gap-2">
          <button class="btn-secondary" @click="showResetPasswordModal = false">Cancel</button>
          <button class="btn-primary" :disabled="isLoading || !newPassword || newPassword !== confirmPassword" @click="resetPassword">
            Reset Password
          </button>
        </div>
      </template>
    </BaseModal>

    <!-- Change Own Password Modal -->
    <BaseModal :open="showChangePasswordModal" @update:open="showChangePasswordModal = $event" title="Change Your Password" max-width="max-w-md">
      <div class="space-y-4">
        <div>
          <label class="label">Current Password</label>
          <input v-model="currentPassword" type="password" class="input w-full" />
        </div>
        <div>
          <label class="label">New Password</label>
          <input v-model="newPassword" type="password" class="input w-full" />
        </div>
        <div>
          <label class="label">Confirm New Password</label>
          <input v-model="confirmPassword" type="password" class="input w-full" />
        </div>
      </div>
      <template #footer>
        <div class="flex justify-end gap-2">
          <BaseButton
            variant="secondary"
            :disabled="isLoading"
            @click="showChangePasswordModal = false"
          >
            Cancel
          </BaseButton>
          <BaseButton
            variant="primary"
            :disabled="isLoading || !currentPassword || !newPassword || newPassword !== confirmPassword"
            @click="changeOwnPassword"
          >
            Change Password
          </BaseButton>
        </div>
      </template>
    </BaseModal>
  </div>
</template>

<style scoped>
/* B7.1: Role badges nutzen Design-Tokens (NICHT error/red fuer Admin). */
.role-badge {
  border: 1px solid transparent;
}

.role-badge--admin {
  color: var(--color-accent, var(--color-iridescent-2));
  background: color-mix(in srgb, var(--color-accent, var(--color-iridescent-2)) 10%, transparent);
  border-color: color-mix(in srgb, var(--color-accent, var(--color-iridescent-2)) 30%, transparent);
}

.role-badge--operator {
  color: var(--color-warning);
  background: color-mix(in srgb, var(--color-warning) 10%, transparent);
  border-color: color-mix(in srgb, var(--color-warning) 30%, transparent);
}

.role-badge--viewer {
  color: var(--color-info);
  background: color-mix(in srgb, var(--color-info) 10%, transparent);
  border-color: color-mix(in srgb, var(--color-info) 30%, transparent);
}
</style>


















