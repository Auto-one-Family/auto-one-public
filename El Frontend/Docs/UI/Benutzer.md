# 👥 User-Management - Vollständige UI-Dokumentation

## 📋 Sektion 1: Übersicht

### **Route und Zugriff**
- **URL**: `/users`
- **Zugriffsberechtigung**: Ausschließlich Administratoren (ADMIN-Rolle erforderlich)
- **Zweck**: Vollständige User-Administration und Account-Management
- **Zielgruppe**: Systemadministratoren für User-Verwaltung

### **Kernfunktionen**
- **CRUD-Operationen**: Vollständiges Erstellen, Lesen, Aktualisieren und Löschen von User-Konten
- **Rollen-Management**: Zuweisung und Änderung von Benutzerrollen (ADMIN/USER)
- **Password-Management**: Sicheres Zurücksetzen von Passwörtern durch Administratoren
- **Account-Status**: Aktivierung/Deaktivierung von User-Konten (Soft-Delete)
- **Suchen & Filtern**: Erweiterte Filteroptionen nach Username, E-Mail, Rolle und Status
- **Bulk-Operationen**: Mehrfachauswahl für gleichzeitige Aktionen
- **Audit-Trail**: Vollständige Nachverfolgung aller User-Änderungen
- **Datenexport**: CSV/XML-Export der User-Daten für Berichterstattung

### **Technische Architektur**
- **Frontend**: React/TypeScript mit modernen UI-Komponenten
- **Backend**: RESTful API mit JWT-Authentifizierung
- **Datenbank**: Relationale Datenbank mit User-Tabelle und Audit-Logs
- **Security**: BCrypt-Password-Hashing, Token-basierte Authentifizierung
- **Performance**: Lazy-Loading, Pagination für große User-Listen

### **Business-Logic**
- **Onboarding-Flow**: Einladung neuer User per E-Mail mit temporären Credentials
- **Access-Control**: Rollenbasierte Berechtigungen (RBAC)
- **Security-Policies**: Automatische Deaktivierung inaktiver Accounts
- **Compliance**: GDPR-konforme Datenverarbeitung mit Löschfunktionen

---

## 🎨 Sektion 2: UI-Komponenten detailliert

### **Hauptlayout - UserManagementView**

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│ 👥 User-Management Dashboard                                                  │
├─────────────────────────────────────────────────────────────────────────────────┤
│ [➕ Neuen User erstellen] [🔄 Aktualisieren] [📊 Export CSV] [📋 Bulk Actions ▼] │
├─────────────────────────────────────────────────────────────────────────────────┤
│ Suchen & Filtern:                                                              │
│ ┌─────────────────┬─────────────────┬─────────────────┬───────────────────────┐ │
│ │ 🔍 Username    │ 📧 Email        │ 👥 Rolle ▼      │ 📅 Erstellt ▼         │ │
│ │ [Suchbegriff...]│ [email@domain..]│ [Alle ▼]       │ [Letzte 30 Tage ▼]    │ │
│ └─────────────────┴─────────────────┴─────────────────┴───────────────────────┘ │
├─────────────────────────────────────────────────────────────────────────────────┤
│ User-Tabelle (sortierbar, paginiert):                                          │
│ ┌────┬────────────┬────────────────────┬────────┬────────────┬────────┬─────────┐ │
│ │ ID │ Username   │ Email              │ Rolle  │ Erstellt   │ Status │ Actions │ │
│ ├────┼────────────┼────────────────────┼────────┼────────────┼────────┼─────────┤ │
│ │ 1  │ admin      │ admin@system.local │ 👑 ADM │ 2024-01-01 │ 🟢 Akt │ ✏️ 🗑️ 🔑 │ │
│ │ 2  │ operator   │ op@company.com    │ 👤 USR │ 2024-02-15 │ 🟢 Akt │ ✏️ 🗑️ 🔑 │ │
│ │ 3  │ analyst    │ ana@company.com   │ 👤 USR │ 2024-03-20 │ 🔴 Inak│ ✏️ ✅ 🔑 │ │
│ │ 4  │ manager    │ mgr@company.com   │ 👑 ADM │ 2024-04-10 │ 🟢 Akt │ ✏️ 🗑️ 🔑 │ │
│ │ 5  │ guest      │ guest@temp.com    │ 👤 USR │ 2024-05-05 │ 🟡 Pend│ ✏️ ✅ 🔑 │ │
│ └────┴────────────┴────────────────────┴────────┴────────────┴────────┴─────────┘ │
│                                                                                   │
│ Pagination: [⬅️ Vorherige] Seite 1 von 5 [Nächste ➡️] Zeilen pro Seite: [25 ▼]  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### **Create/Edit User Modal**

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│ ✏️ User bearbeiten: operator (ID: 2)                                          │
├─────────────────────────────────────────────────────────────────────────────────┤
│ Allgemeine Informationen:                                                       │
│ ┌─────────────────────────────────────────────────────────────────────────────┐ │
│ │ Username:    [operator           ] (3-50 Zeichen, nur a-z, 0-9, _ , -)     │ │
│ │ E-Mail:      [op@company.com     ] (muss gültiges E-Mail-Format haben)      │ │
│ │ Vorname:     [Max                ] (optional, 2-50 Zeichen)                 │ │
│ │ Nachname:    [Mustermann         ] (optional, 2-50 Zeichen)                 │ │
│ └─────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                 │
│ Rollen & Berechtigungen:                                                        │
│ ┌─────────────────────────────────────────────────────────────────────────────┐ │
│ │ Rolle:        [👤 USER ▼          ] (ADMIN = volle Rechte, USER = eingeschränkt)│ │
│ │ Status:       [🟢 Aktiv ▼         ] (Aktiv/Inaktiv/Pending)                  │ │
│ │ Letzte Änderung: 2024-02-15 14:30:22 von admin                              │ │
│ └─────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                 │
│ Password-Management:                                                           │
│ ┌─────────────────────────────────────────────────────────────────────────────┐ │
│ │ [🔄 Password zurücksetzen] (generiert sicheres zufälliges Password)        │ │
│ │ Neues Password: [••••••••••••••••] (mind. 12 Zeichen, Groß/Klein/Sonder)     │ │
│ │ Password bestätigen: [••••••••••••••••] (muss übereinstimmen)                │ │
│ │ [👁️ Sichtbarkeit umschalten]                                               │ │
│ └─────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                 │
│ Account-Einstellungen:                                                          │
│ ┌─────────────────────────────────────────────────────────────────────────────┐ │
│ │ [ ] E-Mail-Benachrichtigungen aktivieren                                     │ │
│ │ [ ] Zwei-Faktor-Authentifizierung erzwingen                                  │ │
│ │ [ ] Password-Änderung bei nächsten Login erzwingen                          │ │
│ │ Account läuft ab am: [2025-02-15    ] (optional, YYYY-MM-DD)                │ │
│ └─────────────────────────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────────────────────────┤
│ [❌ Abbrechen] [💾 Speichern] [🗑️ User löschen]                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### **Bulk-Actions Panel**

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│ 📋 Bulk-Aktionen für 3 ausgewählte User                                        │
├─────────────────────────────────────────────────────────────────────────────────┤
│ Aktion auswählen:                                                               │
│ ┌─────────────────────────────────────────────────────────────────────────────┐ │
│ │ [🟢 Aktivieren     ▼] (für inaktive User)                                    │ │
│ │ [🔴 Deaktivieren   ] (für aktive User)                                      │ │
│ │ [👥 Rolle ändern   ] (ADMIN/USER zuweisen)                                  │ │
│ │ [🗑️ Löschen        ] (Soft-Delete, reversible)                              │ │
│ │ [📧 E-Mail senden  ] (Benachrichtigung an alle)                             │ │
│ └─────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                 │
│ Zusätzliche Optionen:                                                           │
│ ┌─────────────────────────────────────────────────────────────────────────────┐ │
│ │ [ ] Mit Bestätigungsdialog                                                  │ │
│ │ [ ] Audit-Log-Eintrag erstellen                                             │ │
│ │ [ ] E-Mail-Benachrichtigung senden                                          │ │
│ └─────────────────────────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────────────────────────┤
│ [❌ Abbrechen] [⚡ Ausführen]                                                    │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### **Bestätigungsdialoge**

#### **User-Löschung bestätigen:**
```
┌─────────────────────────────────────────────────────────────────────────────────┐
│ ⚠️ User wirklich löschen?                                                      │
├─────────────────────────────────────────────────────────────────────────────────┤
│ Sind Sie sicher, dass Sie den User "operator" (ID: 2) löschen möchten?         │
│                                                                                 │
│ Diese Aktion führt zu:                                                         │
│ • Soft-Delete des User-Accounts (Daten bleiben erhalten)                       │
│ • Sofortige Deaktivierung aller Sessions                                       │
│ • Eintrag im Audit-Log                                                         │
│ • Benachrichtigung per E-Mail (falls aktiviert)                                │
│                                                                                 │
│ Der User kann später wieder aktiviert werden.                                  │
├─────────────────────────────────────────────────────────────────────────────────┤
│ [❌ Nein, abbrechen] [🗑️ Ja, User löschen]                                      │
└─────────────────────────────────────────────────────────────────────────────────┘
```

#### **Password-Reset bestätigen:**
```
┌─────────────────────────────────────────────────────────────────────────────────┐
│ 🔑 Password zurücksetzen?                                                      │
├─────────────────────────────────────────────────────────────────────────────────┤
│ Ein neues zufälliges Password für "operator" wird generiert.                   │
│                                                                                 │
│ Das neue Password:                                                              │
│ • Wird automatisch per E-Mail zugestellt                                       │
│ • Muss beim nächsten Login geändert werden                                     │
│ • Ist 12+ Zeichen lang mit Sonderzeichen                                       │
│ • Wird im Audit-Log protokolliert                                              │
├─────────────────────────────────────────────────────────────────────────────────┤
│ [❌ Abbrechen] [🔄 Password zurücksetzen]                                       │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### **Status-Indikatoren und Badges**

| Status | Icon | Bedeutung | Farbe | Aktion verfügbar |
|--------|------|-----------|-------|------------------|
| Aktiv | 🟢 | User kann sich anmelden | Grün (#22c55e) | Alle Aktionen |
| Inaktiv | 🔴 | User ist deaktiviert | Rot (#ef4444) | Aktivieren, Bearbeiten |
| Pending | 🟡 | User noch nicht bestätigt | Gelb (#eab308) | Aktivieren, Löschen |
| Expired | ⚫ | Account abgelaufen | Grau (#6b7280) | Reaktivieren, Löschen |

### **Toast-Benachrichtigungen**

```
✅ User "analyst" erfolgreich erstellt
❌ Fehler: E-Mail-Adresse bereits vergeben
⚠️ Warnung: Schwaches Password - bitte stärkeres wählen
ℹ️ Info: 5 User erfolgreich aktiviert
```

---

## 🔄 Sektion 3: User-Management Interaktionen

### **3.1 Create User Flow**

#### **Schritt-für-Schritt Prozess:**

1. **Button-Click**: Administrator klickt "➕ Neuen User erstellen"
2. **Modal öffnet**: CreateUserModal wird angezeigt mit leeren Formularfeldern
3. **Formulareingabe**: Admin gibt Username, E-Mail, Rolle ein
4. **Password-Generierung**: System generiert sicheres Initial-Password automatisch
5. **Validierung**: Client-seitige Validierung aller Eingaben
6. **API-Call**: POST /api/v1/users mit User-Daten
7. **Feedback**: Toast-Benachrichtigung über Erfolg/Fehler
8. **Modal schließt**: Bei Erfolg, Tabelle aktualisiert sich automatisch

#### **Validierungsregeln:**
- **Username**: 3-50 Zeichen, nur a-z, 0-9, _, -
- **E-Mail**: Gültiges E-Mail-Format, einzigartig in System
- **Rolle**: Pflichtfeld (ADMIN oder USER)
- **Password**: Automatisch generiert (12+ Zeichen, alle Charaktertypen)

#### **Fehlerbehandlung:**
- Username bereits vergeben → Feld markieren, Fokus setzen
- E-Mail bereits vergeben → Feld markieren, Vorschlag anzeigen
- Netzwerkfehler → Retry-Button anzeigen
- Server-Validation-Fehler → Spezifische Fehlermeldungen anzeigen

### **3.2 Edit User Flow**

#### **Interaktionsablauf:**

1. **User auswählen**: Klick auf "✏️" in der Actions-Spalte
2. **Edit-Modal öffnet**: Vorab gefüllt mit aktuellen User-Daten
3. **Änderungen vornehmen**: Admin modifiziert Felder (außer Username)
4. **Validierung**: Echtzeit-Validierung während Eingabe
5. **Änderungen speichern**: PUT /api/v1/users/{id}
6. **Audit-Log**: Automatische Protokollierung der Änderungen
7. **UI aktualisiert**: Tabelle zeigt neue Daten

#### **Bearbeitbare Felder:**
- ✅ E-Mail-Adresse
- ✅ Vorname/Nachname
- ✅ Rolle (nur von ADMIN zu USER oder umgekehrt)
- ✅ Account-Status (Aktiv/Inaktiv)
- ✅ Account-Ablaufdatum
- ❌ Username (nicht änderbar aus Sicherheitsgründen)

#### **Spezielle Validierungen:**
- E-Mail-Änderung: Prüfung auf Einzigartigkeit
- Rollenänderung: Bestätigungsdialog bei ADMIN→USER
- Statusänderung: Grund für Änderung erforderlich

### **3.3 Delete User Flow**

#### **Soft-Delete Implementierung:**

1. **Lösch-Button klicken**: "🗑️" in Actions-Spalte
2. **Bestätigungsdialog**: Detaillierte Warnung mit Konsequenzen
3. **Admin bestätigt**: Mit zusätzlichen Optionen (E-Mail-Benachrichtigung)
4. **API-Call**: DELETE /api/v1/users/{id} (Soft-Delete)
5. **Status-Update**: User wird als "Inaktiv" markiert
6. **Sessions beenden**: Sofortige Invalidierung aller Tokens
7. **Audit-Eintrag**: Vollständige Lösch-Dokumentation

#### **Wiederherstellungsoptionen:**
- User kann durch Admin reaktiviert werden
- Alle Daten bleiben in Datenbank erhalten
- Historie bleibt vollständig zugänglich

### **3.4 Password Reset Flow**

#### **Administrator-initiiertes Reset:**

1. **Reset-Button**: "🔑" in Actions-Spalte klicken
2. **Bestätigungsdialog**: Mit Sicherheitswarnungen
3. **Password-Generierung**: Serverseitige Erstellung sicherer Credentials
4. **API-Call**: POST /api/v1/users/{id}/reset-password
5. **E-Mail-Versand**: Automatische Benachrichtigung an User
6. **Audit-Logging**: Vollständige Dokumentation des Resets
7. **UI-Feedback**: Erfolgsmeldung mit Reset-Details

#### **Password-Policies:**
- Mindestens 12 Zeichen
- Groß- und Kleinbuchstaben erforderlich
- Mindestens 1 Ziffer und 1 Sonderzeichen
- Keine Wiederverwendung der letzten 5 Passwörter
- Automatische Generierung mit crypto-safe RNG

### **3.5 Bulk Operations Flow**

#### **Mehrfachauswahl und Aktionen:**

1. **User auswählen**: Checkboxen in Tabellenzeilen aktivieren
2. **Bulk-Panel öffnet**: Automatisch bei Mehrfachauswahl
3. **Aktion wählen**: Dropdown mit verfügbaren Bulk-Operationen
4. **Optionen konfigurieren**: Zusätzliche Einstellungen (E-Mail, Audit)
5. **Bestätigung**: Sicherheitsdialog vor Ausführung
6. **Batch-Verarbeitung**: Parallele API-Calls für Performance
7. **Progress-Anzeige**: Live-Update des Fortschritts
8. **Ergebnis-Report**: Detaillierte Rückmeldung über Erfolg/Fehler

#### **Verfügbare Bulk-Aktionen:**
- **Status-Änderung**: Aktivieren/Deaktivieren mehrerer User
- **Rollen-Änderung**: Massenweise Rollen-Zuweisung
- **Löschen**: Soft-Delete mehrerer Accounts
- **E-Mail-Benachrichtigung**: Nachricht an alle ausgewählten User
- **Export**: CSV-Export der ausgewählten User-Daten

### **3.6 Search & Filter Interactions**

#### **Erweiterte Suchfunktionen:**

1. **Live-Search**: Sofortige Filterung bei Eingabe (debounced)
2. **Mehrfach-Filter**: Kombination verschiedener Kriterien
3. **Saved Filters**: Benutzerdefinierte Filtersets speichern
4. **Filter-Historie**: Zuletzt verwendete Filter wiederherstellen
5. **Export gefilterter Daten**: Suchergebnisse exportieren

#### **Filter-Kriterien:**
- **Username**: Teilstring-Suche (case-insensitive)
- **E-Mail**: Domain-basierte Filterung möglich
- **Rolle**: ADMIN, USER, oder beide
- **Status**: Aktiv, Inaktiv, Pending
- **Erstellungsdatum**: Datumsbereich-Filterung
- **Letzte Aktivität**: Zeitbasierte Filter

### **3.7 Pagination & Sorting**

#### **Performance-Optimierung:**

1. **Server-side Pagination**: Nur sichtbare Daten laden
2. **Sortierung**: Multi-Column-Sorting möglich
3. **Page Size**: Anpassbar (10, 25, 50, 100 Zeilen)
4. **Lazy Loading**: Automatisches Nachladen bei Scrollen
5. **Cache-Optimierung**: Browser-Caching für statische Daten

#### **UX-Features:**
- **Page Jump**: Direkte Seitennavigation
- **First/Last**: Schnellzugriff auf erste/letzte Seite
- **Results Counter**: "X von Y User angezeigt"
- **Loading States**: Skeletton-Loader während Daten laden

### **3.8 Real-time Updates**

#### **Live-Daten-Synchronisation:**

1. **WebSocket-Verbindung**: Server-push für Updates
2. **Auto-Refresh**: Konfigurierbarer Timer (30s - 5min)
3. **Change Detection**: Automatische Aktualisierung bei Änderungen
4. **Conflict Resolution**: Merge-Strategien bei gleichzeitigen Änderungen
5. **Offline-Support**: Lokaler Cache bei Netzwerkproblemen

#### **Update-Typen:**
- **User-Status-Änderungen**: Sofortige Sichtbarkeit
- **Neue User**: Live-Hinzufügung zur Tabelle
- **Bulk-Operationen**: Progress-Updates und finale Ergebnisse
- **Session-Expiry**: Automatische Logout-Benachrichtigung

---

## 🔌 Sektion 4: Server-API Integration

### **4.1 API-Architektur Übersicht**

#### **Basis-Konfiguration:**
- **Base-URL**: `/api/v1/users`
- **Authentication**: JWT Bearer Token erforderlich
- **Content-Type**: `application/json`
- **Rate Limiting**: 100 Requests/Minute pro User
- **CORS**: Konfiguriert für Frontend-Domain
- **Versioning**: API-Version in URL-Pfad

#### **Response-Format Standard:**
```json
{
  "success": true,
  "data": { /* Payload */ },
  "message": "Operation successful",
  "timestamp": "2024-01-01T12:00:00Z",
  "requestId": "req-12345"
}
```

#### **Error-Response Format:**
```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Username already exists",
    "details": {
      "field": "username",
      "value": "existing_user"
    }
  },
  "timestamp": "2024-01-01T12:00:00Z",
  "requestId": "req-12345"
}
```

### **4.2 CRUD-API Endpoints**

#### **GET /api/v1/users - User-Liste abrufen**

**Request:**
```
GET /api/v1/users?page=1&limit=25&sort=username&order=asc&role=USER&status=active&search=john
Authorization: Bearer <jwt-token>
```

**Query-Parameter:**
- `page` (integer): Seitennummer (1-basiert)
- `limit` (integer): Zeilen pro Seite (10, 25, 50, 100)
- `sort` (string): Sortierfeld (id, username, email, role, created_at, status)
- `order` (string): Sortierreihenfolge (asc, desc)
- `role` (string): Filter nach Rolle (ADMIN, USER)
- `status` (string): Filter nach Status (active, inactive, pending)
- `search` (string): Volltextsuche in username/email
- `created_after` (date): Nur User nach diesem Datum
- `created_before` (date): Nur User vor diesem Datum

**Response:**
```json
{
  "success": true,
  "data": {
    "users": [
      {
        "id": 1,
        "username": "admin",
        "email": "admin@system.local",
        "firstName": "System",
        "lastName": "Administrator",
        "role": "ADMIN",
        "status": "active",
        "createdAt": "2024-01-01T00:00:00Z",
        "updatedAt": "2024-01-01T00:00:00Z",
        "lastLogin": "2024-01-15T14:30:00Z",
        "loginCount": 42,
        "expiresAt": null,
        "emailVerified": true
      }
    ],
    "pagination": {
      "page": 1,
      "limit": 25,
      "total": 150,
      "totalPages": 6,
      "hasNext": true,
      "hasPrev": false
    },
    "filters": {
      "applied": ["role=USER", "status=active"],
      "available": ["role", "status", "created_date"]
    }
  }
}
```

#### **POST /api/v1/users - Neuen User erstellen**

**Request:**
```json
POST /api/v1/users
Authorization: Bearer <jwt-token>
Content-Type: application/json

{
  "username": "newuser",
  "email": "newuser@company.com",
  "firstName": "New",
  "lastName": "User",
  "role": "USER",
  "status": "active",
  "sendEmail": true,
  "emailTemplate": "user_invitation",
  "expiresAt": "2025-01-01T00:00:00Z"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "user": {
      "id": 151,
      "username": "newuser",
      "email": "newuser@company.com",
      "role": "USER",
      "status": "active",
      "createdAt": "2024-01-15T16:45:00Z",
      "tempPassword": "TempPass123!@#"
    },
    "emailSent": true,
    "auditId": "audit-789"
  },
  "message": "User created successfully"
}
```

#### **PUT /api/v1/users/{id} - User aktualisieren**

**Request:**
```json
PUT /api/v1/users/2
Authorization: Bearer <jwt-token>
Content-Type: application/json

{
  "email": "updated@company.com",
  "firstName": "Updated",
  "lastName": "Name",
  "role": "ADMIN",
  "status": "active",
  "expiresAt": "2025-06-01T00:00:00Z",
  "changeReason": "Promoted to administrator"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "user": {
      "id": 2,
      "username": "operator",
      "email": "updated@company.com",
      "role": "ADMIN",
      "status": "active",
      "updatedAt": "2024-01-15T17:00:00Z"
    },
    "changes": [
      {"field": "email", "oldValue": "op@company.com", "newValue": "updated@company.com"},
      {"field": "role", "oldValue": "USER", "newValue": "ADMIN"}
    ],
    "auditId": "audit-790"
  }
}
```

#### **DELETE /api/v1/users/{id} - User löschen (Soft-Delete)**

**Request:**
```json
DELETE /api/v1/users/3
Authorization: Bearer <jwt-token>
Content-Type: application/json

{
  "reason": "User requested account deletion",
  "notifyUser": true,
  "hardDelete": false
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "userId": 3,
    "action": "soft_delete",
    "status": "inactive",
    "deletedAt": "2024-01-15T17:30:00Z",
    "auditId": "audit-791",
    "emailSent": true
  },
  "message": "User deactivated successfully"
}
```

### **4.3 Spezialisierte API Endpoints**

#### **POST /api/v1/users/{id}/reset-password - Password zurücksetzen**

**Request:**
```json
POST /api/v1/users/2/reset-password
Authorization: Bearer <jwt-token>
Content-Type: application/json

{
  "sendEmail": true,
  "forceChange": true,
  "reason": "Security policy violation"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "userId": 2,
    "newPassword": "SecurePass456!@#",
    "emailSent": true,
    "expiresAt": "2024-01-15T18:00:00Z",
    "auditId": "audit-792"
  }
}
```

#### **POST /api/v1/users/bulk - Bulk-Operationen**

**Request:**
```json
POST /api/v1/users/bulk
Authorization: Bearer <jwt-token>
Content-Type: application/json

{
  "action": "status_update",
  "userIds": [1, 2, 3, 4, 5],
  "parameters": {
    "status": "active",
    "reason": "Bulk activation after audit"
  },
  "options": {
    "notifyUsers": true,
    "createAuditEntries": true,
    "rollbackOnError": true
  }
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "operationId": "bulk-op-123",
    "action": "status_update",
    "totalUsers": 5,
    "successful": 5,
    "failed": 0,
    "results": [
      {"userId": 1, "status": "success", "newStatus": "active"},
      {"userId": 2, "status": "success", "newStatus": "active"}
    ],
    "auditId": "audit-793"
  }
}
```

#### **GET /api/v1/users/export - Daten exportieren**

**Request:**
```
GET /api/v1/users/export?format=csv&role=USER&status=active&fields=username,email,role,created_at
Authorization: Bearer <jwt-token>
Accept: text/csv
```

**Response Headers:**
```
Content-Type: text/csv
Content-Disposition: attachment; filename="users_export_2024-01-15.csv"
```

**CSV Response:**
```csv
id,username,email,role,status,created_at,last_login
1,admin,admin@system.local,ADMIN,active,2024-01-01T00:00:00Z,2024-01-15T14:30:00Z
2,operator,updated@company.com,ADMIN,active,2024-02-15T10:00:00Z,2024-01-14T09:15:00Z
```

### **4.4 Authentication & Authorization**

#### **JWT-Token Struktur:**
```json
{
  "sub": "admin",
  "userId": 1,
  "role": "ADMIN",
  "permissions": ["users.read", "users.write", "users.delete", "audit.read"],
  "iat": 1642156800,
  "exp": 1642160400,
  "iss": "user-management-api",
  "aud": "frontend-client"
}
```

#### **Role-Based Access Control (RBAC):**
```json
{
  "ADMIN": {
    "permissions": [
      "users.read", "users.write", "users.delete", "users.reset_password",
      "users.bulk_operations", "audit.read", "system.config"
    ],
    "restrictions": []
  },
  "USER": {
    "permissions": ["users.read_own", "profile.update"],
    "restrictions": ["no_bulk_ops", "no_delete", "no_admin_users"]
  }
}
```

#### **Middleware Chain:**
1. **CORS-Validation**: Ursprungsdomain prüfen
2. **Rate Limiting**: Request-Frequenz überwachen
3. **JWT-Validation**: Token-Integrität und Expiration prüfen
4. **Role-Checking**: Berechtigungen für Endpoint validieren
5. **Audit-Logging**: Alle Requests automatisch protokollieren
6. **Request-Validation**: Input-Daten sanitizen und validieren

### **4.5 Error Handling & Status Codes**

| HTTP Status | Error Code | Beschreibung | Client Action |
|-------------|------------|--------------|---------------|
| 400 | VALIDATION_ERROR | Ungültige Eingabedaten | Felder hervorheben, korrigieren |
| 401 | UNAUTHORIZED | Kein gültiger Token | Login-Seite anzeigen |
| 403 | FORBIDDEN | Unzureichende Berechtigungen | Zugriff verweigert anzeigen |
| 404 | USER_NOT_FOUND | User existiert nicht | User-liste aktualisieren |
| 409 | CONFLICT | Username/E-Mail bereits vergeben | Alternative vorschlagen |
| 429 | RATE_LIMIT_EXCEEDED | Zu viele Requests | Retry mit Backoff |
| 500 | INTERNAL_ERROR | Serverfehler | Generische Fehlermeldung |

### **4.6 Performance & Caching**

#### **Caching-Strategien:**
- **User-Liste**: Redis-Cache für 5 Minuten
- **User-Details**: Cache für 10 Minuten mit Invalidierung bei Updates
- **Role-Data**: Langzeit-Cache (1 Stunde) mit manueller Invalidierung
- **Audit-Logs**: Kein Cache für Sicherheitsgründe

#### **Database-Optimierung:**
- **Indexes**: Auf username, email, role, status, created_at
- **Pagination**: Cursor-basierte Pagination für große Datasets
- **Connection Pooling**: Prepared Statements für wiederholte Queries
- **Read Replicas**: Lese-Operationen von Replicas

#### **API-Performance-Metriken:**
- **Response Time**: <200ms für einfache Queries, <500ms für komplexe
- **Throughput**: 1000+ Requests/Minute
- **Error Rate**: <1% Ziel für alle Endpoints
- **Cache Hit Rate**: >90% für User-Listen

---

## 🔒 Sektion 5: Security & Validation

### **5.1 Authentifizierung & Autorisierung**

#### **JWT-Token Security:**
- **Algorithmus**: RS256 (RSA-Signatur) für maximale Sicherheit
- **Expiration**: Access-Token: 15 Minuten, Refresh-Token: 7 Tage
- **Claims**: Minimale Payload mit essential User-Daten
- **Revocation**: Sofortige Invalidierung bei Security-Events
- **Rotation**: Automatische Token-Rotation bei jedem Request

#### **Session-Management:**
```json
{
  "sessionId": "sess-12345",
  "userId": 1,
  "ipAddress": "192.168.1.100",
  "userAgent": "Mozilla/5.0...",
  "createdAt": "2024-01-15T10:00:00Z",
  "lastActivity": "2024-01-15T10:30:00Z",
  "expiresAt": "2024-01-15T10:45:00Z",
  "isActive": true
}
```

#### **Multi-Faktor-Authentifizierung (MFA):**
- **Erforderlich für**: Alle ADMIN-User (konfigurierbar)
- **Methoden**: TOTP (Google Authenticator), SMS, E-Mail
- **Grace Period**: 7 Tage für neue MFA-Setup
- **Backup Codes**: 10 Einmal-Codes für Notfälle

### **5.2 Input-Validation & Sanitization**

#### **Client-seitige Validierung:**

**Username-Validierung:**
```javascript
const usernameRegex = /^[a-zA-Z0-9_-]{3,50}$/;
const forbiddenUsernames = ['admin', 'root', 'system', 'guest'];

function validateUsername(username) {
  if (!usernameRegex.test(username)) {
    return { valid: false, error: 'Invalid format' };
  }
  if (forbiddenUsernames.includes(username.toLowerCase())) {
    return { valid: false, error: 'Reserved username' };
  }
  return { valid: true };
}
```

**E-Mail-Validierung:**
```javascript
const emailRegex = /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$/;

function validateEmail(email) {
  if (!emailRegex.test(email)) {
    return { valid: false, error: 'Invalid email format' };
  }
  if (email.length > 254) {
    return { valid: false, error: 'Email too long' };
  }
  return { valid: true };
}
```

**Password-Policy:**
```javascript
function validatePassword(password) {
  const minLength = 12;
  const hasUpper = /[A-Z]/.test(password);
  const hasLower = /[a-z]/.test(password);
  const hasNumber = /\d/.test(password);
  const hasSpecial = /[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?]/.test(password);

  if (password.length < minLength) {
    return { valid: false, error: `Minimum ${minLength} characters required` };
  }
  if (!hasUpper || !hasLower || !hasNumber || !hasSpecial) {
    return { valid: false, error: 'Must contain uppercase, lowercase, number, and special character' };
  }

  // Check against common passwords
  if (commonPasswords.includes(password.toLowerCase())) {
    return { valid: false, error: 'Password too common' };
  }

  return { valid: true };
}
```

#### **Server-seitige Validierung:**

**Business-Logic-Validierungen:**
- **E-Mail-Einzigartigkeit**: Case-insensitive Prüfung
- **Username-Einzigartigkeit**: Exakte Übereinstimmung
- **Rollen-Berechtigungen**: Nur ADMIN kann ADMIN-Rollen vergeben
- **Account-Limits**: Maximale User pro Domain/Organisation
- **Rate Limiting**: Anti-Bot-Protection

### **5.3 Password Security**

#### **Hashing & Storage:**
- **Algorithmus**: Argon2id (2024 Standard-Empfehlung)
- **Parameter**: time=2, memory=19456KB, parallelism=1
- **Salt**: 32-Byte cryptographisch sicherer Salt pro User
- **Pepper**: Server-seitiger Pepper für zusätzliche Sicherheit

#### **Password-History:**
- **Speicherung**: Letzte 10 Passwörter gehasht speichern
- **Prüfung**: Keine Wiederverwendung der letzten 5 Passwörter
- **Aufbewahrung**: 2 Jahre für Compliance-Zwecke

#### **Brute-Force-Protection:**
- **Login Attempts**: Max. 5 Versuche pro 15 Minuten
- **Progressive Delays**: Exponentielle Backoff-Strategie
- **IP-Blocking**: Temporäres Blockieren nach zu vielen Fehlversuchen
- **Captcha**: Nach 3 Fehlversuchen erforderlich

### **5.4 Audit Logging**

#### **Audit-Event-Typen:**

```json
{
  "eventId": "audit-12345",
  "timestamp": "2024-01-15T14:30:22Z",
  "eventType": "USER_CREATED",
  "actor": {
    "userId": 1,
    "username": "admin",
    "ipAddress": "192.168.1.100",
    "userAgent": "Mozilla/5.0..."
  },
  "target": {
    "resourceType": "USER",
    "resourceId": 151,
    "resourceName": "newuser"
  },
  "action": {
    "operation": "CREATE",
    "endpoint": "/api/v1/users",
    "method": "POST",
    "parameters": {
      "username": "newuser",
      "email": "newuser@company.com",
      "role": "USER"
    }
  },
  "result": {
    "success": true,
    "changes": [
      {"field": "username", "newValue": "newuser"},
      {"field": "email", "newValue": "newuser@company.com"}
    ]
  },
  "metadata": {
    "sessionId": "sess-67890",
    "requestId": "req-abc123",
    "duration": 245
  }
}
```

#### **Audit-Event-Kategorien:**
- **Authentication**: Login, Logout, Token-Erstellung/-Invalidierung
- **User-Management**: CRUD-Operationen, Password-Resets, Rollenänderungen
- **Security**: Fehlgeschlagene Logins, Permission-Denials, Suspicious Activity
- **System**: Konfigurationsänderungen, Bulk-Operationen, Exports
- **Compliance**: Account-Deaktivierungen, Datenlöschungen, Policy-Verstöße

#### **Audit-Storage:**
- **Datenbank**: Dedizierte Audit-Tabelle mit Partitionierung
- **Retention**: 7 Jahre für Compliance-relevant Events
- **Archivierung**: Automatische Komprimierung nach 1 Jahr
- **Integrity**: Cryptographische Signaturen für Manipulationsschutz
- **Backup**: Tägliche Backups mit 30-tägiger Aufbewahrung

### **5.5 Security Policies**

#### **Account-Security-Policies:**
- **Password-Expiry**: 90 Tage für normale User, 30 Tage für Admins
- **Inactivity-Timeout**: Automatischer Logout nach 30 Minuten Inaktivität
- **Concurrent-Sessions**: Max. 3 gleichzeitige Sessions pro User
- **Device-Tracking**: Bekannte Devices für zusätzliche Sicherheit

#### **Data-Protection:**
- **Encryption at Rest**: AES-256 für sensitive Daten
- **Encryption in Transit**: TLS 1.3 für alle Kommunikation
- **Data Masking**: Automatische Maskierung in Logs
- **GDPR Compliance**: Recht auf Löschung, Datenportabilität

#### **Access-Control:**
- **Principle of Least Privilege**: Minimale erforderliche Berechtigungen
- **Separation of Duties**: Kein User kann kritische Operationen allein ausführen
- **Need-to-Know**: Nur Zugriff auf erforderliche Daten
- **Regular Reviews**: Quartalsweise Überprüfung aller Berechtigungen

### **5.6 Incident Response**

#### **Security-Incident-Prozess:**
1. **Detection**: Automatische Alerts bei verdächtigen Aktivitäten
2. **Assessment**: Sofortige Analyse des Incident-Umfangs
3. **Containment**: Isolation betroffener Systeme/Konten
4. **Recovery**: Wiederherstellung aus sicheren Backups
5. **Lessons Learned**: Post-Incident-Review und Verbesserungen

#### **Monitoring & Alerts:**
- **Real-time Monitoring**: SIEM-System für Security-Events
- **Threshold Alerts**: Bei ungewöhnlichen Aktivitäten
- **Automated Response**: Sofortige Account-Deaktivierung bei Threats
- **Compliance Reporting**: Automatische Berichterstattung bei Incidents

### **5.7 Compliance & Governance**

#### **Compliance-Standards:**
- **GDPR**: Datenschutz-Grundverordnung (EU)
- **SOX**: Sarbanes-Oxley Act (Finanzberichterstattung)
- **ISO 27001**: Informationssicherheits-Management
- **NIST Cybersecurity Framework**: US-amerikanische Standards

#### **Regular Audits:**
- **Internal Audits**: Monatliche Sicherheitsüberprüfungen
- **External Audits**: Jährliche Zertifizierungsaudits
- **Vulnerability Scans**: Wöchentliche automatische Scans
- **Penetration Testing**: Quartalsweise durch externe Experten

#### **Documentation & Reporting:**
- **Security Policies**: Versionierte, genehmigte Richtlinien
- **Risk Assessments**: Jährliche Risikoanalysen
- **Incident Reports**: Detaillierte Dokumentation aller Vorfälle
- **Compliance Reports**: Automatische Generierung für Regulatoren

---

## 🎨 Sektion 6: Design-Spezifikationen & Technische Details

### **6.1 Farbschema & Design-System**

#### **Primäre Farbpalette:**
```css
:root {
  /* Primary Colors */
  --primary-50: #eff6ff;
  --primary-100: #dbeafe;
  --primary-500: #3b82f6;
  --primary-600: #2563eb;
  --primary-700: #1d4ed8;

  /* Status Colors */
  --success-50: #f0fdf4;
  --success-500: #22c55e;
  --success-600: #16a34a;

  --warning-50: #fffbeb;
  --warning-500: #f59e0b;
  --warning-600: #d97706;

  --error-50: #fef2f2;
  --error-500: #ef4444;
  --error-600: #dc2626;

  --info-50: #eff6ff;
  --info-500: #3b82f6;
  --info-600: #2563eb;

  /* Neutral Colors */
  --gray-50: #f9fafb;
  --gray-100: #f3f4f6;
  --gray-200: #e5e7eb;
  --gray-300: #d1d5db;
  --gray-400: #9ca3af;
  --gray-500: #6b7280;
  --gray-600: #4b5563;
  --gray-700: #374151;
  --gray-800: #1f2937;
  --gray-900: #111827;

  /* Semantic Colors for User Management */
  --user-active: var(--success-500);
  --user-inactive: var(--error-500);
  --user-pending: var(--warning-500);
  --admin-badge: var(--primary-600);
  --user-badge: var(--gray-600);
}
```

#### **Design Tokens:**
```css
/* Typography */
--font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
--font-size-xs: 0.75rem;
--font-size-sm: 0.875rem;
--font-size-base: 1rem;
--font-size-lg: 1.125rem;
--font-size-xl: 1.25rem;
--font-size-2xl: 1.5rem;

/* Spacing */
--spacing-1: 0.25rem;
--spacing-2: 0.5rem;
--spacing-3: 0.75rem;
--spacing-4: 1rem;
--spacing-6: 1.5rem;
--spacing-8: 2rem;

/* Border Radius */
--radius-sm: 0.125rem;
--radius-md: 0.375rem;
--radius-lg: 0.5rem;
--radius-xl: 0.75rem;

/* Shadows */
--shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.05);
--shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.1);
--shadow-lg: 0 10px 15px -3px rgb(0 0 0 / 0.1);

/* Transitions */
--transition-fast: 150ms ease-in-out;
--transition-normal: 300ms ease-in-out;
```

### **6.2 Icon-System & Visual Elements**

#### **Status-Icons & Badges:**
```html
<!-- Status Badges -->
<span class="badge badge-active">
  <svg class="icon"><use href="#icon-check-circle"></use></svg>
  Aktiv
</span>

<span class="badge badge-inactive">
  <svg class="icon"><use href="#icon-x-circle"></use></svg>
  Inaktiv
</span>

<span class="badge badge-pending">
  <svg class="icon"><use href="#icon-clock"></use></svg>
  Pending
</span>

<!-- Role Icons -->
<span class="role-badge role-admin">
  <svg class="icon"><use href="#icon-shield"></use></svg>
  ADMIN
</span>

<span class="role-badge role-user">
  <svg class="icon"><use href="#icon-user"></use></svg>
  USER
</span>
```

#### **Action-Button Icons:**
```html
<!-- Primary Actions -->
<button class="btn btn-primary">
  <svg class="icon"><use href="#icon-plus"></use></svg>
  Neuen User erstellen
</button>

<button class="btn btn-secondary">
  <svg class="icon"><use href="#icon-edit"></use></svg>
  Bearbeiten
</button>

<!-- Danger Actions -->
<button class="btn btn-danger">
  <svg class="icon"><use href="#icon-trash"></use></svg>
  Löschen
</button>

<!-- Utility Actions -->
<button class="btn btn-ghost">
  <svg class="icon"><use href="#icon-refresh"></use></svg>
  Aktualisieren
</button>

<button class="btn btn-ghost">
  <svg class="icon"><use href="#icon-export"></use></svg>
  Export
</button>
```

### **6.3 Component-Styling**

#### **User Table Styling:**
```css
.user-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-sm);
  background: white;
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: var(--shadow-sm);
}

.user-table thead th {
  background: var(--gray-50);
  padding: var(--spacing-3) var(--spacing-4);
  text-align: left;
  font-weight: 600;
  color: var(--gray-700);
  border-bottom: 1px solid var(--gray-200);
}

.user-table tbody td {
  padding: var(--spacing-3) var(--spacing-4);
  border-bottom: 1px solid var(--gray-100);
  vertical-align: middle;
}

.user-table tbody tr:hover {
  background: var(--gray-50);
  transition: background-color var(--transition-fast);
}

/* Status column styling */
.status-cell.active {
  color: var(--success-600);
  font-weight: 500;
}

.status-cell.inactive {
  color: var(--error-600);
  font-weight: 500;
}

.status-cell.pending {
  color: var(--warning-600);
  font-weight: 500;
}

/* Action buttons in table */
.action-buttons {
  display: flex;
  gap: var(--spacing-1);
}

.action-buttons button {
  padding: var(--spacing-1) var(--spacing-2);
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.action-buttons .btn-edit:hover {
  background: var(--primary-50);
  color: var(--primary-600);
}

.action-buttons .btn-delete:hover {
  background: var(--error-50);
  color: var(--error-600);
}
```

#### **Modal Styling:**
```css
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  animation: fadeIn 200ms ease-out;
}

.modal-content {
  background: white;
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-lg);
  max-width: 600px;
  width: 90%;
  max-height: 90vh;
  overflow-y: auto;
  animation: slideIn 300ms ease-out;
}

.modal-header {
  padding: var(--spacing-6);
  border-bottom: 1px solid var(--gray-200);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.modal-body {
  padding: var(--spacing-6);
}

.modal-footer {
  padding: var(--spacing-6);
  border-top: 1px solid var(--gray-200);
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-3);
}
```

### **6.4 Form-Validation Styling**

#### **Input Field States:**
```css
.form-field {
  margin-bottom: var(--spacing-4);
}

.form-field label {
  display: block;
  font-weight: 500;
  color: var(--gray-700);
  margin-bottom: var(--spacing-2);
}

.form-field input,
.form-field select {
  width: 100%;
  padding: var(--spacing-3);
  border: 1px solid var(--gray-300);
  border-radius: var(--radius-md);
  font-size: var(--font-size-base);
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
}

.form-field input:focus,
.form-field select:focus {
  outline: none;
  border-color: var(--primary-500);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

/* Validation States */
.form-field.error input,
.form-field.error select {
  border-color: var(--error-500);
  box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.1);
}

.form-field.success input,
.form-field.success select {
  border-color: var(--success-500);
  box-shadow: 0 0 0 3px rgba(34, 197, 94, 0.1);
}

.form-field.warning input,
.form-field.warning select {
  border-color: var(--warning-500);
  box-shadow: 0 0 0 3px rgba(245, 158, 11, 0.1);
}

/* Error Messages */
.error-message {
  color: var(--error-600);
  font-size: var(--font-size-sm);
  margin-top: var(--spacing-1);
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
}

.error-message::before {
  content: '';
  width: 16px;
  height: 16px;
  background: url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg>') no-repeat;
  opacity: 0.8;
}
```

### **6.5 Responsive Design**

#### **Breakpoint-System:**
```css
/* Mobile First Approach */
.user-management {
  padding: var(--spacing-4);
}

/* Tablet */
@media (min-width: 768px) {
  .user-management {
    padding: var(--spacing-6);
  }

  .user-table {
    font-size: var(--font-size-base);
  }
}

/* Desktop */
@media (min-width: 1024px) {
  .user-management {
    padding: var(--spacing-8);
    max-width: 1400px;
    margin: 0 auto;
  }

  .modal-content {
    max-width: 800px;
  }
}

/* Large Desktop */
@media (min-width: 1440px) {
  .user-management {
    padding: var(--spacing-8) var(--spacing-12);
  }
}
```

#### **Mobile-Optimierungen:**
```css
/* Mobile table becomes card layout */
@media (max-width: 767px) {
  .user-table {
    display: none;
  }

  .user-cards {
    display: block;
  }

  .user-card {
    background: white;
    border-radius: var(--radius-lg);
    padding: var(--spacing-4);
    margin-bottom: var(--spacing-4);
    box-shadow: var(--shadow-sm);
  }

  .user-card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: var(--spacing-3);
  }

  .user-card-actions {
    display: flex;
    gap: var(--spacing-2);
  }
}
```

### **6.6 Animationen & Micro-Interactions**

#### **Loading States:**
```css
.skeleton {
  background: linear-gradient(90deg, var(--gray-200) 25%, var(--gray-100) 50%, var(--gray-200) 75%);
  background-size: 200% 100%;
  animation: loading 1.5s infinite;
}

@keyframes loading {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}

/* Button loading state */
.btn.loading {
  position: relative;
  color: transparent;
}

.btn.loading::after {
  content: '';
  position: absolute;
  width: 16px;
  height: 16px;
  top: 50%;
  left: 50%;
  margin-left: -8px;
  margin-top: -8px;
  border: 2px solid var(--gray-300);
  border-top: 2px solid var(--primary-500);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}
```

#### **Success/Error Animations:**
```css
.toast-enter {
  opacity: 0;
  transform: translateY(-100%);
  animation: toastSlideIn 300ms ease-out forwards;
}

.toast-exit {
  animation: toastSlideOut 300ms ease-in forwards;
}

@keyframes toastSlideIn {
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes toastSlideOut {
  to {
    opacity: 0;
    transform: translateX(100%);
  }
}
```

### **6.7 Accessibility (a11y)**

#### **WCAG 2.1 AA Compliance:**
```html
<!-- Semantic HTML -->
<main class="user-management" role="main">
  <h1 id="page-title">User-Management</h1>

  <!-- Properly labeled form elements -->
  <div class="form-field">
    <label for="username-input">Username</label>
    <input
      id="username-input"
      type="text"
      aria-describedby="username-help username-error"
      aria-invalid="false"
      autocomplete="username"
    />
    <div id="username-help" class="help-text">
      3-50 Zeichen, nur Buchstaben, Zahlen, _ und -
    </div>
    <div id="username-error" class="error-message" role="alert" aria-live="polite">
      Username bereits vergeben
    </div>
  </div>

  <!-- Table with proper headers -->
  <table class="user-table" role="table" aria-label="User list">
    <thead>
      <tr>
        <th scope="col">Username</th>
        <th scope="col">E-Mail</th>
        <th scope="col">Rolle</th>
        <th scope="col">Status</th>
        <th scope="col">Aktionen</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td>admin</td>
        <td>admin@system.local</td>
        <td><span class="role-admin" aria-label="Administrator">ADMIN</span></td>
        <td><span class="status-active" aria-label="Account is active">Aktiv</span></td>
        <td>
          <button aria-label="Edit user admin">
            <svg aria-hidden="true"><!-- icon --></svg>
          </button>
        </td>
      </tr>
    </tbody>
  </table>
</main>
```

#### **Keyboard Navigation:**
- **Tab**: Navigiere durch fokussierbare Elemente
- **Enter/Space**: Aktiviere Buttons und Links
- **Escape**: Schließe Modals und Dropdowns
- **Arrow Keys**: Navigiere durch Tabellen und Listen

#### **Screen Reader Support:**
- **Live Regions**: Für dynamische Inhalte und Status-Updates
- **ARIA Labels**: Für Icons und Status-Indikatoren
- **Skip Links**: Direkter Zugang zu Hauptinhalten
- **Focus Management**: Automatischer Fokus bei Modal-Öffnung

### **6.8 Performance-Optimierungen**

#### **Frontend-Performance:**
```javascript
// Lazy loading for components
const UserManagement = lazy(() => import('./UserManagement'));

// Memoization for expensive computations
const UserTable = memo(({ users, onEdit, onDelete }) => {
  // Component logic
});

// Virtual scrolling for large lists
import { FixedSizeList as List } from 'react-window';

// Image optimization
import { lazyload } from 'lazysizes';

// Bundle splitting
const UserModal = lazy(() => import('./modals/UserModal'));
```

#### **Asset-Optimierung:**
```javascript
// Dynamic imports for modals
const handleCreateUser = async () => {
  const { CreateUserModal } = await import('./modals/CreateUserModal');
  // Modal logic
};

// Service Worker for caching
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js');
}
```

### **6.9 Testing-Strategien**

#### **Unit Tests:**
```javascript
describe('UserManagement', () => {
  it('should render user table with correct data', () => {
    const users = [
      { id: 1, username: 'testuser', email: 'test@example.com', role: 'USER' }
    ];

    render(<UserManagement users={users} />);

    expect(screen.getByText('testuser')).toBeInTheDocument();
    expect(screen.getByText('test@example.com')).toBeInTheDocument();
  });

  it('should validate username format', () => {
    const { result } = renderHook(() => useUserValidation());

    expect(result.current.validateUsername('valid_user123')).toBe(true);
    expect(result.current.validateUsername('invalid-user!')).toBe(false);
  });
});
```

#### **Integration Tests:**
```javascript
describe('User Creation Flow', () => {
  it('should create user successfully', async () => {
    // Mock API
    server.use(
      rest.post('/api/v1/users', (req, res, ctx) => {
        return res(ctx.json({
          success: true,
          data: { user: { id: 1, username: 'newuser' } }
        }));
      })
    );

    render(<UserManagement />);

    // User interaction
    userEvent.click(screen.getByText('Neuen User erstellen'));
    userEvent.type(screen.getByLabelText('Username'), 'newuser');
    userEvent.type(screen.getByLabelText('E-Mail'), 'newuser@example.com');
    userEvent.click(screen.getByText('Erstellen'));

    // Assertions
    await waitFor(() => {
      expect(screen.getByText('User erfolgreich erstellt')).toBeInTheDocument();
    });
  });
});
```

#### **E2E Tests:**
```javascript
describe('User Management E2E', () => {
  it('should complete full user lifecycle', () => {
    cy.visit('/users');

    // Login as admin
    cy.login('admin', 'password');

    // Create user
    cy.contains('Neuen User erstellen').click();
    cy.get('[data-testid="username-input"]').type('testuser');
    cy.get('[data-testid="email-input"]').type('test@example.com');
    cy.get('[data-testid="create-button"]').click();

    // Verify creation
    cy.contains('testuser').should('be.visible');

    // Edit user
    cy.get('[data-testid="edit-user-testuser"]').click();
    cy.get('[data-testid="email-input"]').clear().type('updated@example.com');
    cy.get('[data-testid="save-button"]').click();

    // Verify update
    cy.contains('updated@example.com').should('be.visible');

    // Delete user
    cy.get('[data-testid="delete-user-testuser"]').click();
    cy.get('[data-testid="confirm-delete"]').click();

    // Verify deletion
    cy.contains('testuser').should('not.exist');
  });
});
```

---

## 📚 Implementierungs-Guide

### **Technologie-Stack:**
- **Frontend**: React 18 + TypeScript
- **State Management**: Zustand oder Redux Toolkit
- **Styling**: Tailwind CSS + CSS Custom Properties
- **HTTP Client**: Axios mit Request/Response Interceptors
- **Testing**: Jest + React Testing Library + Cypress
- **Build Tool**: Vite für Development, Rollup für Production

### **Projekt-Struktur:**
```
src/
├── components/
│   ├── users/
│   │   ├── UserManagement.tsx
│   │   ├── UserTable.tsx
│   │   ├── UserModal.tsx
│   │   ├── UserFilters.tsx
│   │   └── BulkActions.tsx
├── hooks/
│   ├── useUsers.ts
│   ├── useUserValidation.ts
│   └── useAudit.ts
├── services/
│   ├── userApi.ts
│   └── auditApi.ts
├── types/
│   └── user.ts
├── utils/
│   ├── validation.ts
│   └── formatting.ts
└── styles/
    ├── components.css
    └── theme.css
```

### **Entwicklung-Workflow:**
1. **Planning**: User Stories und Acceptance Criteria definieren
2. **Design**: UI/UX Mockups und Component Breakdown
3. **Development**: TDD-Ansatz mit Unit Tests first
4. **Integration**: API-Integration und End-to-End Tests
5. **Review**: Code Review und Security Audit
6. **Deployment**: Feature Flags und Canary Releases

Diese Dokumentation bietet alle notwendigen Informationen, um das vollständige User-Management-System zu implementieren. Jeder Aspekt von der UI über die API bis hin zur Sicherheit ist detailliert spezifiziert, sodass ein Entwickler das System ohne weitere Rückfragen nachbauen kann.
