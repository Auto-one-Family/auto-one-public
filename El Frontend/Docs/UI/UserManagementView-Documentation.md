# 👥 UserManagementView - Vollständige UI-Dokumentation

## 📋 Übersicht

**Route:** `/users`  
**Zweck:** Vollständige User-Administration für Administratoren  
**Features:** CRUD User-Management, Rollen-Verwaltung, Password-Reset, Audit-Logging  
**Zugangsberechtigung:** Nur ADMIN-Rolle  
**Komponente:** `UserManagementView.vue`

---

## 🎯 UI-Komponenten detailliert

### Hauptlayout der UserManagementView

```vue
<template>
  <div class="user-management-container">
    <!-- Header Toolbar -->
    <div class="user-management-header">
      <h1>👥 User-Management</h1>
      <div class="header-actions">
        <button class="btn-primary" @click="openCreateModal">
          ➕ Neuen User erstellen
        </button>
        <div class="search-filter-section">
          <input
            v-model="searchQuery"
            type="text"
            placeholder="🔍 User suchen..."
            class="search-input"
          />
          <select v-model="roleFilter" class="filter-select">
            <option value="">👥 Alle Rollen</option>
            <option value="ADMIN">👑 ADMIN</option>
            <option value="USER">👤 USER</option>
          </select>
          <select v-model="statusFilter" class="filter-select">
            <option value="">📊 Alle Status</option>
            <option value="active">🟢 Aktiv</option>
            <option value="inactive">🔴 Inaktiv</option>
            <option value="pending">🟡 Pending</option>
          </select>
        </div>
        <button class="btn-secondary" @click="exportUsers">
          📊 Export CSV
        </button>
      </div>
    </div>

    <!-- User Table -->
    <div class="user-table-container">
      <table class="user-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Username</th>
            <th>Email</th>
            <th>Rolle</th>
            <th>Erstellt am</th>
            <th>Letzte Aktivität</th>
            <th>Status</th>
            <th>Aktionen</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="user in filteredUsers" :key="user.id" :class="getUserRowClass(user)">
            <td>{{ user.id }}</td>
            <td>{{ user.username }}</td>
            <td>{{ user.email }}</td>
            <td>
              <span class="role-badge" :class="getRoleClass(user.role)">
                {{ getRoleIcon(user.role) }} {{ user.role }}
              </span>
            </td>
            <td>{{ formatDate(user.createdAt) }}</td>
            <td>{{ formatDate(user.lastActivity) }}</td>
            <td>
              <span class="status-badge" :class="getStatusClass(user.status)">
                {{ getStatusIcon(user.status) }} {{ user.status }}
              </span>
            </td>
            <td class="action-buttons">
              <button class="btn-icon" @click="editUser(user)" title="Bearbeiten">
                ✏️
              </button>
              <button class="btn-icon" @click="resetPassword(user)" title="Password zurücksetzen">
                🔑
              </button>
              <button
                class="btn-icon"
                :class="user.status === 'active' ? 'btn-danger' : 'btn-success'"
                @click="toggleUserStatus(user)"
                :title="user.status === 'active' ? 'Deaktivieren' : 'Aktivieren'"
              >
                {{ user.status === 'active' ? '🗑️' : '✅' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Pagination -->
    <div class="pagination-container" v-if="totalPages > 1">
      <button
        class="pagination-btn"
        :disabled="currentPage === 1"
        @click="currentPage--"
      >
        ◀️ Zurück
      </button>
      <span class="pagination-info">
        Seite {{ currentPage }} von {{ totalPages }}
        ({{ totalUsers }} User gesamt)
      </span>
      <button
        class="pagination-btn"
        :disabled="currentPage === totalPages"
        @click="currentPage++"
      >
        Weiter ▶️
      </button>
    </div>
  </div>

  <!-- Create/Edit Modal -->
  <UserModal
    v-if="showModal"
    :user="selectedUser"
    :isEditing="isEditing"
    @save="handleSaveUser"
    @cancel="closeModal"
  />
</template>
```

### UserModal Komponente (Create/Edit)

```vue
<template>
  <div class="modal-overlay" @click="handleOverlayClick">
    <div class="modal-content user-modal">
      <div class="modal-header">
        <h2>{{ isEditing ? '✏️ User bearbeiten' : '➕ Neuen User erstellen' }}</h2>
        <button class="modal-close" @click="$emit('cancel')">❌</button>
      </div>

      <form @submit.prevent="handleSubmit" class="user-form">
        <div class="form-group">
          <label for="username">Username:</label>
          <input
            id="username"
            v-model="formData.username"
            type="text"
            required
            :class="{ 'error': errors.username }"
            @blur="validateUsername"
          />
          <span class="error-message" v-if="errors.username">{{ errors.username }}</span>
        </div>

        <div class="form-group">
          <label for="email">E-Mail:</label>
          <input
            id="email"
            v-model="formData.email"
            type="email"
            required
            :class="{ 'error': errors.email }"
            @blur="validateEmail"
          />
          <span class="error-message" v-if="errors.email">{{ errors.email }}</span>
        </div>

        <div class="form-group">
          <label for="role">Rolle:</label>
          <select
            id="role"
            v-model="formData.role"
            required
            class="role-select"
          >
            <option value="USER">👤 USER</option>
            <option value="ADMIN">👑 ADMIN</option>
          </select>
        </div>

        <div class="form-group" v-if="!isEditing">
          <label for="password">Initial Password:</label>
          <div class="password-input-container">
            <input
              id="password"
              v-model="formData.password"
              :type="showPassword ? 'text' : 'password'"
              required
              :class="{ 'error': errors.password }"
              @input="validatePassword"
            />
            <button
              type="button"
              class="password-toggle"
              @click="showPassword = !showPassword"
            >
              {{ showPassword ? '🙈' : '👁️' }}
            </button>
          </div>
          <div class="password-strength">
            <div class="strength-bar" :class="passwordStrength.class"></div>
            <span class="strength-text">{{ passwordStrength.text }}</span>
          </div>
          <span class="error-message" v-if="errors.password">{{ errors.password }}</span>
        </div>

        <div class="form-group" v-if="isEditing">
          <label>
            <input
              type="checkbox"
              v-model="formData.forcePasswordReset"
            />
            Password-Reset erzwingen (User muss neues Password setzen)
          </label>
        </div>

        <div class="modal-actions">
          <button type="button" class="btn-secondary" @click="$emit('cancel')">
            ❌ Abbrechen
          </button>
          <button
            type="submit"
            class="btn-primary"
            :disabled="!isFormValid"
          >
            {{ isEditing ? '💾 Speichern' : '✅ Erstellen' }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>
```

---

## 🔄 User-Management Interaktionen

### 1. User erstellen
```javascript
async createUser(userData) {
  try {
    // Client-side Validation
    const validation = this.validateUserData(userData);
    if (!validation.valid) {
      this.showValidationErrors(validation.errors);
      return;
    }

    // Password Strength Check
    if (!this.checkPasswordStrength(userData.password)) {
      this.showError('Password zu schwach');
      return;
    }

    // API Call
    const response = await this.$api.post('/api/v1/users', {
      username: userData.username,
      email: userData.email,
      role: userData.role,
      password: userData.password // Will be hashed server-side
    });

    // Success Handling
    this.showSuccess('User erfolgreich erstellt');
    this.closeModal();
    this.loadUsers();

    // Audit Log
    this.logAuditAction('USER_CREATED', {
      targetUserId: response.data.id,
      changes: { username, email, role }
    });

  } catch (error) {
    this.handleApiError(error);
  }
}
```

### 2. User bearbeiten
```javascript
async updateUser(userId, updateData) {
  try {
    const originalUser = this.users.find(u => u.id === userId);

    // Track changes for audit
    const changes = this.getChanges(originalUser, updateData);

    const response = await this.$api.put(`/api/v1/users/${userId}`, updateData);

    this.showSuccess('User erfolgreich aktualisiert');
    this.closeModal();
    this.loadUsers();

    // Audit Log
    this.logAuditAction('USER_UPDATED', {
      targetUserId: userId,
      changes: changes
    });

  } catch (error) {
    this.handleApiError(error);
  }
}
```

### 3. Password zurücksetzen
```javascript
async resetUserPassword(userId) {
  try {
    // Show confirmation dialog
    const confirmed = await this.showConfirmDialog(
      'Password zurücksetzen',
      'Sind Sie sicher? Der User muss ein neues Password setzen.'
    );

    if (!confirmed) return;

    // Generate temporary password or let server handle it
    const response = await this.$api.post(`/api/v1/users/${userId}/reset-password`);

    this.showSuccess('Password-Reset erfolgreich. User wurde benachrichtigt.');

    // Audit Log
    this.logAuditAction('PASSWORD_RESET', {
      targetUserId: userId,
      initiatedBy: this.currentUser.id
    });

  } catch (error) {
    this.handleApiError(error);
  }
}
```

### 4. User aktivieren/deaktivieren (Soft Delete)
```javascript
async toggleUserStatus(user) {
  try {
    const action = user.status === 'active' ? 'deactivate' : 'activate';
    const newStatus = user.status === 'active' ? 'inactive' : 'active';

    const confirmed = await this.showConfirmDialog(
      `User ${action}`,
      `Sind Sie sicher, dass Sie diesen User ${action} möchten?`
    );

    if (!confirmed) return;

    const response = await this.$api.patch(`/api/v1/users/${user.id}/status`, {
      status: newStatus
    });

    // Update local state
    user.status = newStatus;
    this.showSuccess(`User erfolgreich ${action}d`);

    // Audit Log
    this.logAuditAction('USER_STATUS_CHANGED', {
      targetUserId: user.id,
      oldStatus: user.status,
      newStatus: newStatus
    });

  } catch (error) {
    this.handleApiError(error);
  }
}
```

### 5. Bulk-Operationen
```javascript
async bulkDeactivateUsers(userIds) {
  try {
    const confirmed = await this.showConfirmDialog(
      'Mehrere User deaktivieren',
      `${userIds.length} User werden deaktiviert. Fortfahren?`
    );

    if (!confirmed) return;

    const response = await this.$api.post('/api/v1/users/bulk/status', {
      userIds: userIds,
      status: 'inactive'
    });

    this.showSuccess(`${userIds.length} User erfolgreich deaktiviert`);
    this.loadUsers();

    // Audit Log
    this.logAuditAction('BULK_USER_DEACTIVATION', {
      targetUserIds: userIds,
      count: userIds.length
    });

  } catch (error) {
    this.handleApiError(error);
  }
}
```

---

## 🔗 Server-API Integration

### RESTful Endpoints

```javascript
// User Management API Endpoints
const USER_API_ENDPOINTS = {
  // Get paginated user list (Admin only)
  GET_USERS: 'GET /api/v1/users?page={page}&limit={limit}&search={query}&role={role}&status={status}',

  // Create new user
  CREATE_USER: 'POST /api/v1/users',

  // Get single user details
  GET_USER: 'GET /api/v1/users/{id}',

  // Update user (full update)
  UPDATE_USER: 'PUT /api/v1/users/{id}',

  // Partial update user
  PATCH_USER: 'PATCH /api/v1/users/{id}',

  // Soft delete / deactivate user
  DELETE_USER: 'DELETE /api/v1/users/{id}',

  // Reset user password
  RESET_PASSWORD: 'POST /api/v1/users/{id}/reset-password',

  // Bulk operations
  BULK_STATUS_UPDATE: 'POST /api/v1/users/bulk/status',
  BULK_DELETE: 'POST /api/v1/users/bulk/delete',

  // User statistics
  GET_USER_STATS: 'GET /api/v1/users/stats'
};
```

### API Request/Response Beispiele

#### Create User Request
```json
POST /api/v1/users
Authorization: Bearer <admin-jwt-token>
Content-Type: application/json

{
  "username": "newuser",
  "email": "newuser@example.com",
  "role": "USER",
  "password": "SecurePass123!",
  "sendWelcomeEmail": true
}
```

#### Create User Response (Success)
```json
{
  "success": true,
  "data": {
    "id": 42,
    "username": "newuser",
    "email": "newuser@example.com",
    "role": "USER",
    "status": "pending",
    "createdAt": "2024-12-27T10:30:00Z",
    "createdBy": "admin",
    "requiresPasswordReset": true
  },
  "message": "User erfolgreich erstellt"
}
```

#### Get Users List Request
```json
GET /api/v1/users?page=1&limit=10&role=USER&status=active&search=john
Authorization: Bearer <admin-jwt-token>
```

#### Get Users List Response
```json
{
  "success": true,
  "data": {
    "users": [
      {
        "id": 1,
        "username": "john_doe",
        "email": "john@example.com",
        "role": "USER",
        "status": "active",
        "createdAt": "2024-01-15T08:30:00Z",
        "lastActivity": "2024-12-26T14:22:00Z",
        "loginCount": 45
      }
    ],
    "pagination": {
      "page": 1,
      "limit": 10,
      "total": 156,
      "totalPages": 16
    },
    "filters": {
      "role": "USER",
      "status": "active",
      "search": "john"
    }
  }
}
```

### Error Response Format
```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Validierung fehlgeschlagen",
    "details": {
      "username": "Username bereits vergeben",
      "email": "Ungültiges E-Mail Format"
    }
  }
}
```

---

## 🔐 Security & Validation

### Authentication & Authorization
```javascript
// JWT Token Structure for Admin Users
const adminJwtPayload = {
  sub: "user-123",           // User ID
  username: "admin",
  email: "admin@example.com",
  role: "ADMIN",             // Required for user management access
  permissions: [
    "users.read",
    "users.create",
    "users.update",
    "users.delete",
    "users.reset_password",
    "audit.read"
  ],
  iat: 1640995200,
  exp: 1641081600
};

// Route Guard Implementation
router.beforeEach((to, from, next) => {
  if (to.path === '/users') {
    if (!isAuthenticated()) {
      next('/login');
      return;
    }

    if (!hasRole('ADMIN')) {
      next('/unauthorized');
      return;
    }
  }
  next();
});
```

### Input Validation Rules
```javascript
const USER_VALIDATION_RULES = {
  username: {
    required: true,
    minLength: 3,
    maxLength: 50,
    pattern: /^[a-zA-Z0-9_-]+$/,
    unique: true
  },
  email: {
    required: true,
    maxLength: 255,
    pattern: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
    unique: true
  },
  password: {
    required: true,
    minLength: 8,
    maxLength: 128,
    pattern: /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]/,
    strength: {
      weak: /.{8,}/,
      medium: /(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}/,
      strong: /(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&]).{8,}/
    }
  },
  role: {
    required: true,
    allowedValues: ['USER', 'ADMIN']
  }
};
```

### Audit Logging
```javascript
const AUDIT_EVENTS = {
  USER_CREATED: 'user_created',
  USER_UPDATED: 'user_updated',
  USER_DELETED: 'user_deleted',
  USER_STATUS_CHANGED: 'user_status_changed',
  PASSWORD_RESET: 'password_reset',
  BULK_OPERATION: 'bulk_operation',
  LOGIN_ATTEMPT: 'login_attempt',
  PERMISSION_DENIED: 'permission_denied'
};

// Audit Log Entry Structure
const auditLogEntry = {
  id: 'audit-123',
  timestamp: '2024-12-27T10:30:00Z',
  eventType: 'USER_CREATED',
  actor: {
    id: 'admin-456',
    username: 'admin',
    ip: '192.168.1.100',
    userAgent: 'Mozilla/5.0...'
  },
  target: {
    type: 'user',
    id: 'user-789',
    username: 'newuser'
  },
  changes: {
    username: { old: null, new: 'newuser' },
    email: { old: null, new: 'newuser@example.com' },
    role: { old: null, new: 'USER' }
  },
  metadata: {
    sessionId: 'session-abc',
    apiEndpoint: '/api/v1/users',
    httpMethod: 'POST'
  }
};
```

---

## 🎨 Styling & Design

### CSS Classes und Design-System
```css
/* User Management Container */
.user-management-container {
  padding: 20px;
  background: #f8f9fa;
  min-height: 100vh;
}

/* Header Section */
.user-management-header {
  background: white;
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
  margin-bottom: 20px;
}

.header-actions {
  display: flex;
  gap: 15px;
  align-items: center;
  margin-top: 15px;
  flex-wrap: wrap;
}

/* Search and Filter */
.search-input, .filter-select {
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 14px;
}

.search-input {
  min-width: 250px;
}

.filter-select {
  min-width: 120px;
}

/* User Table */
.user-table {
  width: 100%;
  background: white;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.user-table th {
  background: #f8f9fa;
  padding: 15px;
  text-align: left;
  font-weight: 600;
  border-bottom: 2px solid #dee2e6;
}

.user-table td {
  padding: 12px 15px;
  border-bottom: 1px solid #dee2e6;
}

/* Status and Role Badges */
.status-badge, .role-badge {
  padding: 4px 8px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.status-badge.active { background: #d4edda; color: #155724; }
.status-badge.inactive { background: #f8d7da; color: #721c24; }
.status-badge.pending { background: #fff3cd; color: #856404; }

.role-badge.ADMIN { background: #e7f3ff; color: #0066cc; }
.role-badge.USER { background: #f0f0f0; color: #666; }

/* Action Buttons */
.action-buttons {
  display: flex;
  gap: 8px;
}

.btn-icon {
  background: none;
  border: none;
  cursor: pointer;
  padding: 6px;
  border-radius: 4px;
  transition: background-color 0.2s;
}

.btn-icon:hover {
  background: #f8f9fa;
}

.btn-danger:hover { background: #f8d7da; }
.btn-success:hover { background: #d4edda; }

/* Modal Styles */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0,0,0,0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: white;
  border-radius: 8px;
  width: 90%;
  max-width: 500px;
  max-height: 90vh;
  overflow-y: auto;
}

.modal-header {
  padding: 20px;
  border-bottom: 1px solid #dee2e6;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.modal-close {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: #6c757d;
}

/* Form Styles */
.user-form {
  padding: 20px;
}

.form-group {
  margin-bottom: 20px;
}

.form-group label {
  display: block;
  margin-bottom: 5px;
  font-weight: 500;
}

.form-group input,
.form-group select {
  width: 100%;
  padding: 10px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 14px;
}

.form-group input.error {
  border-color: #dc3545;
}

.error-message {
  color: #dc3545;
  font-size: 12px;
  margin-top: 4px;
  display: block;
}

/* Password Strength Indicator */
.password-strength {
  margin-top: 8px;
}

.strength-bar {
  height: 4px;
  border-radius: 2px;
  margin-bottom: 4px;
}

.strength-bar.weak { background: #dc3545; width: 33%; }
.strength-bar.medium { background: #ffc107; width: 66%; }
.strength-bar.strong { background: #28a745; width: 100%; }

.strength-text {
  font-size: 12px;
  color: #6c757d;
}

/* Button Styles */
.btn-primary {
  background: #007bff;
  color: white;
  border: none;
  padding: 10px 20px;
  border-radius: 4px;
  cursor: pointer;
  font-weight: 500;
}

.btn-primary:hover {
  background: #0056b3;
}

.btn-primary:disabled {
  background: #6c757d;
  cursor: not-allowed;
}

.btn-secondary {
  background: #6c757d;
  color: white;
  border: none;
  padding: 10px 20px;
  border-radius: 4px;
  cursor: pointer;
}

.btn-secondary:hover {
  background: #545b62;
}

/* Pagination */
.pagination-container {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 20px;
  margin-top: 20px;
  padding: 20px;
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.pagination-btn {
  padding: 8px 16px;
  border: 1px solid #ddd;
  background: white;
  border-radius: 4px;
  cursor: pointer;
}

.pagination-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.pagination-info {
  font-weight: 500;
  color: #6c757d;
}

/* Responsive Design */
@media (max-width: 768px) {
  .header-actions {
    flex-direction: column;
    align-items: stretch;
  }

  .user-table {
    font-size: 14px;
  }

  .user-table th,
  .user-table td {
    padding: 8px;
  }

  .action-buttons {
    flex-direction: column;
    gap: 4px;
  }
}
```

---

## 🚀 Implementierungshinweise

### Vue.js Komponente Setup
```javascript
export default {
  name: 'UserManagementView',
  data() {
    return {
      users: [],
      filteredUsers: [],
      searchQuery: '',
      roleFilter: '',
      statusFilter: '',
      currentPage: 1,
      pageSize: 10,
      totalUsers: 0,
      totalPages: 0,
      showModal: false,
      isEditing: false,
      selectedUser: null,
      loading: false,
      errors: {}
    };
  },
  computed: {
    currentUser() {
      return this.$store.state.auth.user;
    },
    hasAdminRole() {
      return this.currentUser?.role === 'ADMIN';
    }
  },
  watch: {
    searchQuery() { this.filterUsers(); },
    roleFilter() { this.filterUsers(); },
    statusFilter() { this.filterUsers(); }
  },
  async mounted() {
    if (!this.hasAdminRole) {
      this.$router.push('/unauthorized');
      return;
    }
    await this.loadUsers();
  },
  methods: {
    // Implementation methods as shown above
  }
};
```

### Performance Optimizations
- **Pagination**: Server-side pagination für große User-Listen
- **Debounced Search**: 300ms Verzögerung bei Such-Eingaben
- **Virtual Scrolling**: Bei >1000 Usern virtuelle Listen verwenden
- **Lazy Loading**: User-Details nur bei Bedarf laden

### Error Handling
- **Network Errors**: Automatische Retry-Logik mit exponentiellem Backoff
- **Validation Errors**: Feld-spezifische Fehlermeldungen
- **Permission Errors**: Klare Unauthorized-Meldungen
- **Server Errors**: User-friendly Fehlerbehandlung

---

## 📊 Monitoring & Analytics

### User Management Metrics
```javascript
const USER_METRICS = {
  totalUsers: 0,
  activeUsers: 0,
  inactiveUsers: 0,
  adminUsers: 0,
  newUsersToday: 0,
  newUsersThisWeek: 0,
  passwordResetsToday: 0,
  failedLoginAttempts: 0,
  averageSessionDuration: 0
};
```

### Audit Dashboard Integration
- **Real-time Audit Stream**: Live-Updates für kritische Aktionen
- **Export Capabilities**: CSV/JSON Export für Compliance
- **Search & Filter**: Audit-Logs durchsuchbar machen
- **Retention Policy**: Automatische Löschung alter Audit-Einträge

---

Diese Dokumentation bietet eine vollständige Übersicht über die UserManagementView Implementierung. Der Fokus liegt auf Sicherheit, Benutzerfreundlichkeit und Wartbarkeit. Alle CRUD-Operationen sind abgedeckt, mit besonderer Berücksichtigung von Admin-Rechten, Audit-Logging und Input-Validation.
