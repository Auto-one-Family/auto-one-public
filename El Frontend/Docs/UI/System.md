# ⚙️ System-Konfiguration - Vollständige UI-Dokumentation

## 🎯 Übersicht

### Route: `/system-config`
**Zweck**: Server-Konfiguration dynamisch ändern (Admin-only)
**Berechtigung**: Administrator-Rechte erforderlich
**Features**: Live-Editing, Echtzeit-Validierung, Backup/Restore, Hot-Reload

### Hauptfunktionen
- **Dynamische Konfiguration**: Server-Einstellungen ohne Neustart ändern
- **Live-Validierung**: Sofortige Rückmeldung zu Konfigurationsfehlern
- **Backup-System**: Automatische Sicherungen vor kritischen Änderungen
- **Template-Management**: Vorgefertigte Konfigurationen für verschiedene Umgebungen
- **Hot-Reload**: Automatische Anwendung von Änderungen ohne Server-Restart

---

## 🔍 Layout & Design

### UI-Struktur
Die SystemConfigView verwendet ein zweispaltiges Layout mit konfigurierbaren Bereichen:

```
┌─────────────────────────────────────────────────────────┐
│ 🔧 System Configuration - Live Config Editor           │
├─────────────────────────────────────────────────────────┤
│ [💾 Save Changes] [🔄 Reset] [📦 Backup] [📥 Restore]   │
│ [🎭 Templates ▼] [🔍 Validate] [⚡ Hot-Reload]          │
├─────────────────┬───────────────────────────────────────┤
│ Config Sections │ Settings Editor                      │
│ ┌─────────────┐ │ ┌───────────────────────────────────┐ │
│ │ 🌐 Network  │ │ │ Host: [localhost     ]  🟢         │ │
│ │ 🔌 MQTT     │ │ │ Port: [8000          ]  🟢 (1-65535)│ │
│ │ 💾 Database │ │ │ SSL:  [✓             ]  🟢         │ │
│ │ 🔒 Security │ │ │                                     │ │
│ │ 📊 Logging  │ │ │ MQTT Broker: [localhost] 🟢        │ │
│ │ 🎭 Misc     │ │ │ MQTT Port:   [1883    ] 🟢         │ │
│ └─────────────┘ │ │ MQTT User:   [        ] 🟢         │ │
│                 │ │ MQTT Pass:   [••••••• ] 🟢         │ │
│                 │ └─────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘

📊 Validation Status Panel:
┌─────────────────────────────────────────────────────────┐
│ 🟢 Network: All settings valid                            │
│ 🟢 MQTT: Connection successful                           │
│ ⚠️  Database: Connection timeout (retrying...)          │
│ 🔴 Security: Weak password policy detected              │
│ 🟢 Logging: Configuration valid                          │
│ 🟡 Misc: Deprecated feature flag in use                 │
└─────────────────────────────────────────────────────────┘
```

### Navigation & Tabs
- **Vertikale Sidebar**: Config-Kategorien mit Icons
- **Aktive Markierung**: Blaue Hervorhebung für ausgewählte Kategorie
- **Badge-Indikatoren**: Fehler/Warnungen pro Kategorie anzeigen

### Toolbar Elemente
- **💾 Save Changes**: Alle Änderungen speichern (mit Bestätigungsdialog)
- **🔄 Reset**: Alle ungespeicherten Änderungen verwerfen
- **📦 Backup**: Manuelles Backup der aktuellen Konfiguration
- **📥 Restore**: Backup wiederherstellen aus Dropdown-Liste
- **🎭 Templates**: Vorgefertigte Konfigurationen laden
- **🔍 Validate**: Manuelle Validierung aller Einstellungen
- **⚡ Hot-Reload**: Sofortige Anwendung ohne Speicherung

---

## 🎛️ Interaktive Elemente

### Input-Typen & Controls

#### Text Inputs
```vue
<template>
  <div class="config-input-group">
    <label class="config-label">Server Host</label>
    <input
      type="text"
      v-model="config.network.host"
      @input="validateField('network.host')"
      class="config-input text-input"
      placeholder="localhost"
    />
    <span class="validation-icon" :class="getValidationClass('network.host')">
      {{ getValidationIcon('network.host') }}
    </span>
  </div>
</template>
```

#### Number Inputs mit Range-Validierung
```vue
<template>
  <div class="config-input-group">
    <label class="config-label">Server Port</label>
    <input
      type="number"
      v-model.number="config.network.port"
      @input="validateField('network.port')"
      class="config-input number-input"
      :min="1"
      :max="65535"
      placeholder="8000"
    />
    <small class="range-hint">(1-65535)</small>
  </div>
</template>
```

#### Boolean Toggles
```vue
<template>
  <div class="config-input-group">
    <label class="config-label">Enable SSL</label>
    <div class="toggle-container">
      <input
        type="checkbox"
        v-model="config.network.ssl"
        @change="validateField('network.ssl')"
        class="config-toggle"
        id="ssl-toggle"
      />
      <label for="ssl-toggle" class="toggle-slider"></label>
      <span class="toggle-label">{{ config.network.ssl ? 'Enabled' : 'Disabled' }}</span>
    </div>
  </div>
</template>
```

#### Password/Secret Fields
```vue
<template>
  <div class="config-input-group">
    <label class="config-label">MQTT Password</label>
    <div class="password-input-container">
      <input
        :type="showPassword ? 'text' : 'password'"
        v-model="config.mqtt.password"
        @input="validateField('mqtt.password')"
        class="config-input password-input"
        placeholder="Enter password"
      />
      <button
        type="button"
        @click="showPassword = !showPassword"
        class="password-toggle"
      >
        {{ showPassword ? '🙈' : '👁️' }}
      </button>
    </div>
  </div>
</template>
```

### Dropdowns & Selects
```vue
<template>
  <div class="config-input-group">
    <label class="config-label">Log Level</label>
    <select
      v-model="config.logging.level"
      @change="validateField('logging.level')"
      class="config-select"
    >
      <option value="DEBUG">DEBUG</option>
      <option value="INFO">INFO</option>
      <option value="WARNING">WARNING</option>
      <option value="ERROR">ERROR</option>
      <option value="CRITICAL">CRITICAL</option>
    </select>
  </div>
</template>
```

### Validierung & Feedback

#### Echtzeit-Validierung
```javascript
methods: {
  async validateField(fieldPath) {
    try {
      const response = await fetch('/api/v1/debug/config/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          field: fieldPath,
          value: this.getNestedValue(fieldPath),
          config: this.config
        })
      });

      const result = await response.json();
      this.validationResults[fieldPath] = result;
      this.updateValidationStatus();
    } catch (error) {
      console.error('Validation error:', error);
    }
  },

  updateValidationStatus() {
    this.validationSummary = {
      valid: Object.values(this.validationResults).filter(r => r.status === 'valid').length,
      warnings: Object.values(this.validationResults).filter(r => r.status === 'warning').length,
      errors: Object.values(this.validationResults).filter(r => r.status === 'error').length
    };
  }
}
```

#### Validation States
- **🟢 Valid**: Feld ist korrekt konfiguriert
- **🟡 Warning**: Feld funktioniert aber könnte optimiert werden
- **🔴 Error**: Feld ist fehlerhaft und muss korrigiert werden
- **⏳ Pending**: Validierung läuft (für Server-seitige Checks)

---

## 🔌 Server-API Integration

### Config-API Endpoints

#### GET /api/v1/debug/config
**Zweck**: Aktuelle Server-Konfiguration laden
```javascript
// Request
GET /api/v1/debug/config
Authorization: Bearer <admin-token>

// Response
{
  "status": "success",
  "data": {
    "network": {
      "host": "localhost",
      "port": 8000,
      "ssl": false
    },
    "mqtt": {
      "broker": "localhost",
      "port": 1883,
      "username": "",
      "password": ""
    },
    "database": {
      "connection_string": "postgresql://user:pass@localhost:5432/db",
      "pool_size": 10,
      "timeout": 30
    },
    "security": {
      "password_min_length": 8,
      "token_timeout": 3600,
      "max_login_attempts": 5
    },
    "logging": {
      "level": "INFO",
      "rotation": "daily",
      "max_files": 30
    },
    "misc": {
      "feature_flags": ["experimental_ui", "debug_mode"],
      "rate_limits": {
        "requests_per_minute": 100,
        "burst_limit": 20
      }
    }
  },
  "metadata": {
    "last_modified": "2024-01-15T10:30:00Z",
    "environment": "development",
    "version": "1.2.3"
  }
}
```

#### PUT /api/v1/debug/config
**Zweck**: Konfigurationsänderungen speichern
```javascript
// Request
PUT /api/v1/debug/config
Authorization: Bearer <admin-token>
Content-Type: application/json

{
  "changes": {
    "network.port": 8080,
    "mqtt.broker": "mqtt.example.com"
  },
  "create_backup": true,
  "hot_reload": true
}

// Response
{
  "status": "success",
  "message": "Configuration updated successfully",
  "backup_id": "backup_20240115_103000",
  "hot_reload_status": "applied",
  "requires_restart": false
}
```

#### POST /api/v1/debug/config/validate
**Zweck**: Konfiguration server-seitig validieren
```javascript
// Request
POST /api/v1/debug/config/validate
Authorization: Bearer <admin-token>
Content-Type: application/json

{
  "config": { /* full config object */ },
  "fields": ["network", "database"], // optional: only validate specific sections
  "strict": true // optional: fail on warnings
}

// Response
{
  "status": "success",
  "results": {
    "network": {
      "status": "valid",
      "message": "Network configuration is valid"
    },
    "database": {
      "status": "warning",
      "message": "Connection timeout is high, consider reducing",
      "suggestions": ["Reduce timeout to 15 seconds"]
    }
  },
  "summary": {
    "valid": 1,
    "warnings": 1,
    "errors": 0
  }
}
```

#### POST /api/v1/debug/config/backup
**Zweck**: Konfigurations-Backup erstellen
```javascript
// Request
POST /api/v1/debug/config/backup
Authorization: Bearer <admin-token>
Content-Type: application/json

{
  "name": "pre_deployment_backup", // optional custom name
  "description": "Backup before production deployment"
}

// Response
{
  "status": "success",
  "backup_id": "backup_20240115_103000",
  "filename": "config_backup_20240115_103000.json",
  "size": 2456,
  "created_at": "2024-01-15T10:30:00Z"
}
```

#### POST /api/v1/debug/config/restore
**Zweck**: Konfiguration aus Backup wiederherstellen
```javascript
// Request
POST /api/v1/debug/config/restore
Authorization: Bearer <admin-token>
Content-Type: application/json

{
  "backup_id": "backup_20240115_103000",
  "hot_reload": true,
  "create_backup_before_restore": true
}

// Response
{
  "status": "success",
  "message": "Configuration restored successfully",
  "from_backup": "backup_20240115_103000",
  "hot_reload_status": "applied",
  "backup_created": "backup_20240115_103100"
}
```

### Hot-Reload System
Das Hot-Reload System ermöglicht die dynamische Anwendung von Konfigurationsänderungen ohne Server-Neustart:

```javascript
// Client-seitige Implementierung
async function applyHotReload(changes) {
  try {
    const response = await fetch('/api/v1/debug/config/hot-reload', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${this.adminToken}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        changes: changes,
        rollback_on_error: true,
        timeout: 30000
      })
    });

    const result = await response.json();

    if (result.status === 'success') {
      this.showNotification('Hot-reload applied successfully', 'success');
      // Update local config state
      this.mergeChanges(changes);
    } else {
      throw new Error(result.message);
    }
  } catch (error) {
    this.showNotification(`Hot-reload failed: ${error.message}`, 'error');
    // Optionally rollback changes
    await this.rollbackChanges();
  }
}
```

---

## 📊 Konfigurations-Kategorien

### 🌐 Network Configuration
```json
{
  "network": {
    "host": "localhost",
    "port": 8000,
    "ssl": {
      "enabled": false,
      "cert_file": "/path/to/cert.pem",
      "key_file": "/path/to/key.pem",
      "ca_file": "/path/to/ca.pem"
    },
    "cors": {
      "enabled": true,
      "origins": ["http://localhost:3000", "https://app.example.com"],
      "methods": ["GET", "POST", "PUT", "DELETE"],
      "headers": ["Content-Type", "Authorization"]
    },
    "rate_limiting": {
      "enabled": true,
      "requests_per_minute": 100,
      "burst_limit": 20
    }
  }
}
```

**Validierungsregeln**:
- Host: Muss gültiger Hostname oder IP-Adresse sein
- Port: 1-65535, nicht belegt von anderen Services
- SSL: Zertifikat-Dateien müssen existieren und gültig sein

### 🔌 MQTT Configuration
```json
{
  "mqtt": {
    "broker": "localhost",
    "port": 1883,
    "username": "",
    "password": "",
    "client_id": "god_kaiser_server",
    "topics": {
      "command": "gk/commands",
      "status": "gk/status",
      "sensor": "gk/sensor/+",
      "actuator": "gk/actuator/+"
    },
    "qos": 1,
    "retain": false,
    "keepalive": 60,
    "reconnect_delay": 5000,
    "ssl": {
      "enabled": false,
      "ca_certs": "/path/to/ca.crt",
      "certfile": "/path/to/client.crt",
      "keyfile": "/path/to/client.key"
    }
  }
}
```

**Validierungsregeln**:
- Broker: Muss erreichbar sein
- Port: Standard 1883 (MQTT) oder 8883 (MQTT-S)
- Credentials: Optional, aber wenn gesetzt dann beide erforderlich

### 💾 Database Configuration
```json
{
  "database": {
    "type": "postgresql",
    "connection_string": "postgresql://user:password@localhost:5432/god_kaiser",
    "pool": {
      "min_connections": 5,
      "max_connections": 20,
      "max_idle_time": 300,
      "max_lifetime": 3600
    },
    "timeout": 30,
    "ssl_mode": "require",
    "backup": {
      "enabled": true,
      "schedule": "0 2 * * *",
      "retention_days": 30
    }
  }
}
```

**Validierungsregeln**:
- Connection String: Muss korrektes Format haben
- Verbindung: Muss erfolgreich hergestellt werden können
- Pool Settings: min_connections <= max_connections

### 🔒 Security Configuration
```json
{
  "security": {
    "authentication": {
      "method": "jwt",
      "token_expiry": 3600,
      "refresh_token_expiry": 86400,
      "secret_key": "your-secret-key-here"
    },
    "password_policy": {
      "min_length": 8,
      "require_uppercase": true,
      "require_lowercase": true,
      "require_numbers": true,
      "require_special_chars": false
    },
    "session": {
      "timeout": 1800,
      "max_concurrent_sessions": 5,
      "remember_me_days": 30
    },
    "rate_limiting": {
      "login_attempts_per_hour": 5,
      "api_requests_per_minute": 100
    }
  }
}
```

### 📊 Logging Configuration
```json
{
  "logging": {
    "level": "INFO",
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    "handlers": [
      {
        "type": "file",
        "filename": "/var/log/god_kaiser/server.log",
        "max_bytes": 10485760,
        "backup_count": 5
      },
      {
        "type": "console",
        "stream": "stdout"
      }
    ],
    "loggers": {
      "sqlalchemy": "WARNING",
      "aiohttp": "INFO",
      "mqtt": "DEBUG"
    }
  }
}
```

### 🎭 Miscellaneous Configuration
```json
{
  "misc": {
    "feature_flags": {
      "experimental_ui": false,
      "debug_mode": false,
      "performance_monitoring": true,
      "auto_backup": true
    },
    "limits": {
      "max_file_upload_size": 10485760,
      "max_request_size": 1048576,
      "max_concurrent_requests": 100
    },
    "timeouts": {
      "request_timeout": 30,
      "database_timeout": 10,
      "mqtt_timeout": 5
    },
    "maintenance": {
      "auto_cleanup_interval": 3600,
      "health_check_interval": 60,
      "metrics_retention_days": 7
    }
  }
}
```

---

## 🎨 Design-Spezifikationen

### Color Coding
```css
/* Input Types */
.config-input.text-input {
  border-left: 4px solid #3b82f6; /* blue-500 */
}

.config-input.number-input {
  border-left: 4px solid #10b981; /* emerald-500 */
}

.config-toggle:checked + .toggle-slider {
  background-color: #10b981;
}

/* Validation States */
.validation-valid {
  color: #10b981; /* green */
  border-color: #10b981;
}

.validation-warning {
  color: #f59e0b; /* amber */
  border-color: #f59e0b;
}

.validation-error {
  color: #ef4444; /* red */
  border-color: #ef4444;
}

/* Critical Settings */
.critical-setting {
  border: 2px solid #ef4444;
  background-color: #fef2f2;
}

.critical-setting:focus {
  box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.1);
}
```

### Icons & Indicators
- **🟢**: Valid (green circle)
- **🟡**: Warning (yellow triangle)
- **🔴**: Error (red circle)
- **⏳**: Pending validation (hourglass)
- *****: Changed field (asterisk)
- **🔒**: Critical setting (lock)

### Responsive Design
```css
/* Mobile Layout */
@media (max-width: 768px) {
  .system-config-container {
    flex-direction: column;
  }

  .config-sidebar {
    width: 100%;
    height: auto;
    border-bottom: 1px solid #e5e7eb;
  }

  .config-editor {
    width: 100%;
  }

  .toolbar {
    flex-wrap: wrap;
    gap: 0.5rem;
  }
}
```

---

## 🔧 Technische Implementierung

### Vue.js Komponente
```vue
<template>
  <div class="system-config-view">
    <ConfigToolbar
      :hasChanges="hasUnsavedChanges"
      :validationSummary="validationSummary"
      @save="handleSave"
      @reset="handleReset"
      @backup="handleBackup"
      @restore="handleRestore"
      @validate="handleValidate"
      @hot-reload="handleHotReload"
    />

    <div class="config-container">
      <ConfigSidebar
        :categories="configCategories"
        :activeCategory="activeCategory"
        :validationResults="validationResults"
        @select-category="activeCategory = $event"
      />

      <ConfigEditor
        :config="config"
        :category="activeCategory"
        :validationResults="validationResults"
        @update-config="handleConfigUpdate"
        @validate-field="validateField"
      />
    </div>

    <ValidationPanel
      :validationResults="validationResults"
      :isValidating="isValidating"
    />
  </div>
</template>

<script>
import ConfigToolbar from './components/ConfigToolbar.vue'
import ConfigSidebar from './components/ConfigSidebar.vue'
import ConfigEditor from './components/ConfigEditor.vue'
import ValidationPanel from './components/ValidationPanel.vue'

export default {
  name: 'SystemConfigView',
  components: {
    ConfigToolbar,
    ConfigSidebar,
    ConfigEditor,
    ValidationPanel
  },

  data() {
    return {
      config: {},
      originalConfig: {},
      validationResults: {},
      activeCategory: 'network',
      isValidating: false,
      adminToken: localStorage.getItem('admin_token')
    }
  },

  computed: {
    hasUnsavedChanges() {
      return JSON.stringify(this.config) !== JSON.stringify(this.originalConfig)
    },

    validationSummary() {
      const results = Object.values(this.validationResults)
      return {
        valid: results.filter(r => r.status === 'valid').length,
        warnings: results.filter(r => r.status === 'warning').length,
        errors: results.filter(r => r.status === 'error').length
      }
    }
  },

  async mounted() {
    await this.loadConfig()
  },

  methods: {
    async loadConfig() {
      try {
        const response = await fetch('/api/v1/debug/config', {
          headers: { 'Authorization': `Bearer ${this.adminToken}` }
        })
        const data = await response.json()
        this.config = data.data
        this.originalConfig = JSON.parse(JSON.stringify(data.data))
      } catch (error) {
        this.showError('Failed to load configuration')
      }
    },

    async handleSave() {
      if (!this.hasUnsavedChanges) return

      const confirmed = await this.showConfirmDialog(
        'Save Configuration',
        'Are you sure you want to save these changes? This will affect server behavior.'
      )

      if (!confirmed) return

      try {
        const changes = this.getChanges()
        const response = await fetch('/api/v1/debug/config', {
          method: 'PUT',
          headers: {
            'Authorization': `Bearer ${this.adminToken}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            changes,
            create_backup: true,
            hot_reload: true
          })
        })

        const result = await response.json()
        if (result.status === 'success') {
          this.originalConfig = JSON.parse(JSON.stringify(this.config))
          this.showSuccess('Configuration saved successfully')
        } else {
          throw new Error(result.message)
        }
      } catch (error) {
        this.showError(`Save failed: ${error.message}`)
      }
    },

    getChanges() {
      // Calculate diff between current and original config
      return this.deepDiff(this.originalConfig, this.config)
    },

    deepDiff(original, current, path = '') {
      const changes = {}

      for (const key in current) {
        const fullPath = path ? `${path}.${key}` : key

        if (!(key in original)) {
          changes[fullPath] = current[key]
        } else if (typeof current[key] === 'object' && current[key] !== null) {
          const nestedChanges = this.deepDiff(original[key], current[key], fullPath)
          Object.assign(changes, nestedChanges)
        } else if (original[key] !== current[key]) {
          changes[fullPath] = current[key]
        }
      }

      return changes
    }
  }
}
</script>
```

### JSON Schema für Validierung
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "network": {
      "type": "object",
      "properties": {
        "host": {
          "type": "string",
          "format": "hostname",
          "minLength": 1,
          "maxLength": 253
        },
        "port": {
          "type": "integer",
          "minimum": 1,
          "maximum": 65535
        },
        "ssl": {
          "type": "object",
          "properties": {
            "enabled": { "type": "boolean" },
            "cert_file": {
              "type": "string",
              "pattern": "\\.pem$|\\.crt$"
            },
            "key_file": {
              "type": "string",
              "pattern": "\\.pem$|\\.key$"
            }
          }
        }
      },
      "required": ["host", "port"]
    },
    "mqtt": {
      "type": "object",
      "properties": {
        "broker": {
          "type": "string",
          "format": "hostname"
        },
        "port": {
          "type": "integer",
          "minimum": 1,
          "maximum": 65535
        },
        "username": { "type": "string" },
        "password": { "type": "string" }
      },
      "required": ["broker", "port"]
    }
  },
  "required": ["network", "mqtt"]
}
```

---

## 🔄 User-Flows & Workflows

### Standard Workflow: Konfiguration ändern
1. **Zugriff**: Admin navigiert zu `/system-config`
2. **Kategorie wählen**: Gewünschte Konfigurationskategorie auswählen
3. **Änderungen vornehmen**: Werte in entsprechenden Feldern ändern
4. **Live-Validierung**: Automatische Validierung während der Eingabe
5. **Validierung prüfen**: Gesamtstatus in Validation Panel überprüfen
6. **Speichern**: Änderungen speichern mit Backup-Erstellung
7. **Hot-Reload**: Automatische Anwendung der Änderungen

### Kritische Änderungen Workflow
1. **Änderung erkennen**: System erkennt kritische Einstellung
2. **Bestätigung anfordern**: Dialog mit Warnung und Details anzeigen
3. **Backup erzwingen**: Automatisches Backup vor der Änderung
4. **Änderung anwenden**: Mit zusätzlicher Bestätigung speichern
5. **Monitoring**: Erhöhte Überwachung für 5 Minuten nach Änderung

### Troubleshooting Workflow
1. **Problem identifizieren**: Logs/Error-Messages analysieren
2. **Konfiguration prüfen**: Betroffene Einstellungen überprüfen
3. **Backup laden**: Falls nötig frühere funktionierende Konfiguration laden
4. **Änderungen testen**: Mit Hot-Reload oder temporärer Validierung
5. **Permanente Speicherung**: Nach erfolgreichem Test speichern

---

## 🧪 Testing & Quality Assurance

### Unit Tests
```javascript
// ConfigEditor.test.js
describe('ConfigEditor', () => {
  it('validates text input correctly', async () => {
    const wrapper = mount(ConfigEditor, {
      propsData: { config: testConfig, category: 'network' }
    })

    const input = wrapper.find('.text-input')
    await input.setValue('invalid-host-name!')
    await wrapper.vm.validateField('network.host')

    expect(wrapper.vm.validationResults['network.host'].status).toBe('error')
  })

  it('handles hot-reload correctly', async () => {
    const mockApi = jest.spyOn(axios, 'post').mockResolvedValue({
      status: 'success',
      hot_reload_status: 'applied'
    })

    const wrapper = mount(SystemConfigView)
    await wrapper.vm.handleHotReload({ 'network.port': 8080 })

    expect(mockApi).toHaveBeenCalledWith('/api/v1/debug/config/hot-reload', {
      changes: { 'network.port': 8080 },
      rollback_on_error: true,
      timeout: 30000
    })
  })
})
```

### Integration Tests
```javascript
// config-api.test.js
describe('Config API Integration', () => {
  it('saves configuration with backup', async () => {
    const changes = { 'network.port': 8080 }
    const response = await request(app)
      .put('/api/v1/debug/config')
      .set('Authorization', `Bearer ${adminToken}`)
      .send({ changes, create_backup: true })

    expect(response.status).toBe(200)
    expect(response.body.backup_id).toBeDefined()
    expect(response.body.hot_reload_status).toBe('applied')
  })

  it('validates configuration server-side', async () => {
    const config = { network: { host: 'localhost', port: 8000 } }
    const response = await request(app)
      .post('/api/v1/debug/config/validate')
      .set('Authorization', `Bearer ${adminToken}`)
      .send({ config })

    expect(response.status).toBe(200)
    expect(response.body.results.network.status).toBe('valid')
  })
})
```

---

## 📚 API Reference

### Client-side Methods
```javascript
class ConfigManager {
  constructor(apiBaseUrl, adminToken) {
    this.apiBaseUrl = apiBaseUrl
    this.adminToken = adminToken
  }

  // Load current configuration
  async loadConfig() { /* ... */ }

  // Save configuration changes
  async saveConfig(changes, options = {}) { /* ... */ }

  // Validate configuration
  async validateConfig(config, fields = null) { /* ... */ }

  // Create backup
  async createBackup(name = null, description = null) { /* ... */ }

  // Restore from backup
  async restoreBackup(backupId, options = {}) { /* ... */ }

  // Apply hot-reload
  async hotReload(changes) { /* ... */ }

  // Get available templates
  async getTemplates() { /* ... */ }

  // Load template
  async loadTemplate(templateId) { /* ... */ }
}
```

### Error Handling
```javascript
class ConfigError extends Error {
  constructor(message, code, field = null) {
    super(message)
    this.code = code
    this.field = field
    this.name = 'ConfigError'
  }
}

// Error codes
const CONFIG_ERRORS = {
  VALIDATION_FAILED: 'VALIDATION_FAILED',
  SAVE_FAILED: 'SAVE_FAILED',
  BACKUP_FAILED: 'BACKUP_FAILED',
  HOT_RELOAD_FAILED: 'HOT_RELOAD_FAILED',
  PERMISSION_DENIED: 'PERMISSION_DENIED',
  NETWORK_ERROR: 'NETWORK_ERROR'
}
```

---

## 🎯 Fazit

Diese Dokumentation bietet eine vollständige Spezifikation für ein Configuration-Management-System, das es Administratoren ermöglicht, Server-Einstellungen dynamisch und sicher zu ändern. Die Implementierung umfasst:

- **Umfassende UI**: Intuitives Interface mit Live-Validierung
- **Robuste API**: Vollständige CRUD-Operationen mit Backup-System
- **Sicherheit**: Admin-only Zugriff mit Bestätigungsdialogen
- **Flexibilität**: Hot-Reload für sofortige Änderungen
- **Benutzerfreundlichkeit**: Klare Validierungsrückmeldungen und Templates

Ein Entwickler kann mit dieser Dokumentation das komplette System implementieren, von der Vue.js Frontend-Komponente bis zur Python/FastAPI Backend-API.
