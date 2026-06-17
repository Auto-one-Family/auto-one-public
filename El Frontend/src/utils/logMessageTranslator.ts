/**
 * Log-Message-Translator
 *
 * Übersetzt technische Server-Log-Nachrichten in menschenverständliche deutsche Texte.
 * Folgt dem Pattern von errorCodeTranslator.ts für Konsistenz.
 *
 * @module logMessageTranslator
 * @version 1.0.0
 * @since Sprint 3 - UX-Verbesserungen (2026-01-24)
 */

// ============================================================================
// Types
// ============================================================================

export interface TranslatedLogMessage {
  /** Original-Nachricht für technische Referenz */
  original: string
  /** Kurzer, menschenverständlicher Titel */
  title: string
  /** Beschreibung was passiert ist */
  description: string
  /** Lösungsvorschlag für den Benutzer */
  suggestion?: string
  /** Schweregrad der Nachricht */
  severity: 'error' | 'warning' | 'info'
  /** Kategorie für Gruppierung */
  category: LogMessageCategory
}

export type LogMessageCategory =
  | 'file'
  | 'connection'
  | 'esp'
  | 'validation'
  | 'system'
  | 'auth'
  | 'config'
  | 'database'
  | 'mqtt'

interface LogPattern {
  pattern: RegExp
  translate: (match: RegExpMatchArray, original: string) => TranslatedLogMessage
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Extrahiert den Dateinamen aus einem Pfad
 * @example extractFilename('logs\\mosquitto.log') → 'mosquitto.log'
 */
function extractFilename(path: string): string {
  return path.split(/[/\\]/).pop() || path
}

// ============================================================================
// Log Patterns - 15+ Pattern für Production-Ready
// ============================================================================

const LOG_PATTERNS: LogPattern[] = [
  // =========================================================================
  // FILE ERRORS (2 Pattern)
  // =========================================================================
  {
    // [Errno 13] Permission denied: 'logs\\mosquitto.log'
    pattern: /(?:\[Errno \d+\] )?Permission denied:?\s*['"]?([^'"]+)['"]?/i,
    translate: (match, original) => ({
      original,
      title: 'Zugriff verweigert',
      description: `Auf die Datei '${extractFilename(match[1])}' kann nicht zugegriffen werden.`,
      suggestion:
        'Prüfen Sie die Dateiberechtigungen oder wenden Sie sich an den Administrator.',
      severity: 'error',
      category: 'file',
    }),
  },
  {
    // [Errno 2] No such file or directory: '/path/to/file'
    pattern: /(?:\[Errno \d+\] )?No such file or directory:?\s*['"]?([^'"]+)['"]?/i,
    translate: (match, original) => ({
      original,
      title: 'Datei nicht gefunden',
      description: `Die Datei '${extractFilename(match[1])}' existiert nicht.`,
      suggestion: 'Stellen Sie sicher, dass der Dateipfad korrekt ist.',
      severity: 'error',
      category: 'file',
    }),
  },

  // =========================================================================
  // CONNECTION ERRORS (4 Pattern)
  // =========================================================================
  {
    // Connection timeout, Connection timed out
    pattern: /Connection\s+(?:timed?\s*out|timeout)/i,
    translate: (_match, original) => ({
      original,
      title: 'Verbindungs-Timeout',
      description: 'Die Verbindung wurde abgebrochen (Zeitüberschreitung).',
      suggestion: 'Prüfen Sie die Netzwerkverbindung und Server-Erreichbarkeit.',
      severity: 'error',
      category: 'connection',
    }),
  },
  {
    // Connection refused
    pattern: /Connection\s+refused/i,
    translate: (_match, original) => ({
      original,
      title: 'Verbindung abgelehnt',
      description: 'Der Zielserver hat die Verbindung abgelehnt.',
      suggestion: 'Prüfen Sie ob der Dienst läuft und die Firewall korrekt konfiguriert ist.',
      severity: 'error',
      category: 'connection',
    }),
  },
  {
    // MQTT connection/broker errors
    pattern: /MQTT.*?(?:connection|broker).*?(?:failed|refused|error|lost)/i,
    translate: (_match, original) => ({
      original,
      title: 'MQTT-Verbindungsfehler',
      description: 'Verbindung zum MQTT-Broker fehlgeschlagen oder unterbrochen.',
      suggestion: 'Prüfen Sie ob der MQTT-Broker (Mosquitto) läuft und erreichbar ist.',
      severity: 'error',
      category: 'mqtt',
    }),
  },
  {
    // Database connection errors
    pattern: /(?:Database|DB|PostgreSQL|psycopg|asyncpg).*?(?:connection|error|failed)/i,
    translate: (_match, original) => ({
      original,
      title: 'Datenbankfehler',
      description: 'Verbindung zur Datenbank fehlgeschlagen oder unterbrochen.',
      suggestion: 'Prüfen Sie ob PostgreSQL läuft und erreichbar ist.',
      severity: 'error',
      category: 'database',
    }),
  },

  // =========================================================================
  // ESP ERRORS (4 Pattern)
  // =========================================================================
  {
    // ESP_XXXXXX disconnected/offline
    pattern: /(ESP_[A-Fa-f0-9]{6,8}).*?(?:disconnected|offline|went offline)/i,
    translate: (match, original) => ({
      original,
      title: 'Gerät offline',
      description: `${match[1].toUpperCase()} ist nicht mehr erreichbar.`,
      suggestion: 'Prüfen Sie Stromversorgung und Netzwerk des Geräts.',
      severity: 'warning',
      category: 'esp',
    }),
  },
  {
    // ESP_XXXXXX timeout
    pattern: /(ESP_[A-Fa-f0-9]{6,8}).*?(?:timeout|timed?\s*out)/i,
    translate: (match, original) => ({
      original,
      title: 'Gerät antwortet nicht',
      description: `${match[1].toUpperCase()} reagiert nicht mehr rechtzeitig.`,
      suggestion: 'Das Gerät ist möglicherweise überlastet oder hat Netzwerkprobleme.',
      severity: 'warning',
      category: 'esp',
    }),
  },
  {
    // Heartbeat missed for ESP_XXXXXX
    pattern: /(?:heartbeat|heart\s*beat).*?(?:missed|timeout|failed).*?(ESP_[A-Fa-f0-9]{6,8})/i,
    translate: (match, original) => ({
      original,
      title: 'Heartbeat verpasst',
      description: `Kein Lebenszeichen von ${match[1].toUpperCase()}.`,
      suggestion: 'Das Gerät sendet keine Heartbeats mehr. Prüfen Sie den Gerätestatus.',
      severity: 'warning',
      category: 'esp',
    }),
  },
  {
    // Alternative: ESP_XXXXXX heartbeat missed (ESP ID zuerst)
    pattern: /(ESP_[A-Fa-f0-9]{6,8}).*?(?:heartbeat|heart\s*beat).*?(?:missed|timeout|failed)/i,
    translate: (match, original) => ({
      original,
      title: 'Heartbeat verpasst',
      description: `Kein Lebenszeichen von ${match[1].toUpperCase()}.`,
      suggestion: 'Das Gerät sendet keine Heartbeats mehr. Prüfen Sie den Gerätestatus.',
      severity: 'warning',
      category: 'esp',
    }),
  },

  // =========================================================================
  // VALIDATION ERRORS (3 Pattern)
  // =========================================================================
  {
    // Validation error: "field_name"
    pattern: /validation.*?error.*?['"]([^'"]+)['"]/i,
    translate: (match, original) => ({
      original,
      title: 'Validierungsfehler',
      description: `Ungültige Daten im Feld: ${match[1]}`,
      suggestion: 'Überprüfen Sie das Datenformat und die Eingabewerte.',
      severity: 'error',
      category: 'validation',
    }),
  },
  {
    // Invalid JSON / JSON parse error
    pattern: /(?:invalid|malformed)\s*JSON|JSON\s*(?:parse|decode)\s*error/i,
    translate: (_match, original) => ({
      original,
      title: 'Ungültiges JSON',
      description: 'Die empfangenen Daten sind kein gültiges JSON-Format.',
      suggestion: 'Prüfen Sie die Datenquelle auf fehlerhafte Formatierung.',
      severity: 'error',
      category: 'validation',
    }),
  },
  {
    // Schema validation failed
    pattern: /schema\s*validation.*?(?:failed|error)/i,
    translate: (_match, original) => ({
      original,
      title: 'Schema-Validierung fehlgeschlagen',
      description: 'Die Datenstruktur entspricht nicht dem erwarteten Schema.',
      suggestion: 'Überprüfen Sie die Datenstruktur und Pflichtfelder.',
      severity: 'error',
      category: 'validation',
    }),
  },

  // =========================================================================
  // SYSTEM ERRORS (3 Pattern)
  // =========================================================================
  {
    // Memory error / Out of memory
    pattern: /(?:memory|heap)\s*(?:error|exhausted)|out\s*of\s*memory/i,
    translate: (_match, original) => ({
      original,
      title: 'Speicherfehler',
      description: 'Der Arbeitsspeicher ist erschöpft.',
      suggestion: 'Starten Sie den Server neu oder erhöhen Sie den verfügbaren RAM.',
      severity: 'error',
      category: 'system',
    }),
  },
  {
    // Disk full / No space left
    pattern: /(?:disk|storage)\s*(?:full|exhausted)|no\s*space\s*left/i,
    translate: (_match, original) => ({
      original,
      title: 'Festplatte voll',
      description: 'Kein Speicherplatz mehr verfügbar.',
      suggestion: 'Löschen Sie nicht benötigte Dateien oder erweitern Sie den Speicher.',
      severity: 'error',
      category: 'system',
    }),
  },
  {
    // Process/Thread crash
    pattern: /(?:process|thread|worker).*?(?:crashed|died|terminated unexpectedly)/i,
    translate: (_match, original) => ({
      original,
      title: 'Prozess abgestürzt',
      description: 'Ein Hintergrundprozess wurde unerwartet beendet.',
      suggestion: 'Prüfen Sie die Server-Logs für weitere Details.',
      severity: 'error',
      category: 'system',
    }),
  },

  // =========================================================================
  // AUTH ERRORS (3 Pattern)
  // =========================================================================
  {
    // Authentication failed / Unauthorized
    pattern: /authentication\s*(?:failed|error)|unauthorized/i,
    translate: (_match, original) => ({
      original,
      title: 'Authentifizierung fehlgeschlagen',
      description: 'Die Anmeldedaten sind ungültig oder fehlen.',
      suggestion: 'Überprüfen Sie Benutzername und Passwort.',
      severity: 'error',
      category: 'auth',
    }),
  },
  {
    // Token expired / JWT expired
    pattern: /(?:token|jwt|session)\s*(?:expired|invalid|revoked)/i,
    translate: (_match, original) => ({
      original,
      title: 'Sitzung abgelaufen',
      description: 'Ihr Login ist nicht mehr gültig.',
      suggestion: 'Bitte melden Sie sich erneut an.',
      severity: 'warning',
      category: 'auth',
    }),
  },
  {
    // Access denied / Forbidden
    pattern: /(?:access|permission)\s*denied|forbidden/i,
    translate: (_match, original) => ({
      original,
      title: 'Zugriff verweigert',
      description: 'Sie haben keine Berechtigung für diese Aktion.',
      suggestion: 'Wenden Sie sich an einen Administrator.',
      severity: 'error',
      category: 'auth',
    }),
  },

  // =========================================================================
  // CONFIG ERRORS (2 Pattern)
  // =========================================================================
  {
    // Config missing / Configuration not found
    pattern: /config(?:uration)?\s*(?:missing|not\s*found)/i,
    translate: (_match, original) => ({
      original,
      title: 'Konfiguration fehlt',
      description: 'Eine erforderliche Konfigurationsdatei wurde nicht gefunden.',
      suggestion: 'Stellen Sie sicher, dass alle Konfigurationsdateien vorhanden sind.',
      severity: 'error',
      category: 'config',
    }),
  },
  {
    // Invalid configuration / Config error
    pattern: /(?:invalid|malformed)\s*config(?:uration)?|config(?:uration)?\s*error/i,
    translate: (_match, original) => ({
      original,
      title: 'Konfigurationsfehler',
      description: 'Die Konfiguration enthält ungültige Werte.',
      suggestion: 'Überprüfen Sie die Konfigurationsdatei auf Syntaxfehler.',
      severity: 'error',
      category: 'config',
    }),
  },
]

// ============================================================================
// Main Functions
// ============================================================================

/**
 * Übersetzt eine technische Log-Nachricht in menschenverständlichen Text.
 *
 * @param message - Die originale Log-Nachricht
 * @returns TranslatedLogMessage oder null wenn kein Pattern matched
 *
 * @example
 * const result = translateLogMessage("Permission denied: 'logs/mosquitto.log'")
 * // result.title === "Zugriff verweigert"
 * // result.description === "Auf die Datei 'mosquitto.log' kann nicht zugegriffen werden."
 */
export function translateLogMessage(message: string): TranslatedLogMessage | null {
  if (!message || typeof message !== 'string') {
    return null
  }

  for (const { pattern, translate } of LOG_PATTERNS) {
    const match = message.match(pattern)
    if (match) {
      return translate(match, message)
    }
  }

  return null // Keine Übersetzung gefunden - Fallback zu Original
}

/**
 * Prüft ob eine Log-Nachricht übersetzt werden kann.
 *
 * @param message - Die zu prüfende Log-Nachricht
 * @returns true wenn eine Übersetzung verfügbar ist
 */
export function canTranslateLogMessage(message: string): boolean {
  return translateLogMessage(message) !== null
}

/**
 * Gibt die Kategorie einer Log-Nachricht zurück.
 *
 * @param message - Die Log-Nachricht
 * @returns Die Kategorie oder null wenn keine Übersetzung verfügbar
 */
export function getLogMessageCategory(message: string): LogMessageCategory | null {
  const translated = translateLogMessage(message)
  return translated?.category ?? null
}

/**
 * Gibt ein passendes Icon für die Kategorie zurück (Lucide Icon Name).
 *
 * @param category - Die Log-Message-Kategorie
 * @returns Lucide Icon Name
 */
export function getCategoryIcon(category: LogMessageCategory): string {
  const icons: Record<LogMessageCategory, string> = {
    file: 'FileX',
    connection: 'WifiOff',
    esp: 'Cpu',
    validation: 'AlertTriangle',
    system: 'Server',
    auth: 'Lock',
    config: 'Settings',
    database: 'Database',
    mqtt: 'Radio',
  }
  return icons[category] || 'AlertCircle'
}

/**
 * Gibt eine deutsche Bezeichnung für die Log-Kategorie zurück.
 *
 * @param category - Die Log-Message-Kategorie
 * @returns Deutsche Bezeichnung
 */
export function getLogCategoryLabel(category: LogMessageCategory): string {
  const labels: Record<LogMessageCategory, string> = {
    file: 'Dateisystem',
    connection: 'Verbindung',
    esp: 'ESP-Gerät',
    validation: 'Validierung',
    system: 'System',
    auth: 'Authentifizierung',
    config: 'Konfiguration',
    database: 'Datenbank',
    mqtt: 'MQTT',
  }
  return labels[category] || 'Unbekannt'
}

/**
 * Gibt ein passendes Icon für die Severity zurück (Lucide Icon Name).
 *
 * @param severity - Der Schweregrad
 * @returns Lucide Icon Name
 */
export function getSeverityIcon(severity: TranslatedLogMessage['severity']): string {
  const icons: Record<TranslatedLogMessage['severity'], string> = {
    error: 'XCircle',
    warning: 'AlertTriangle',
    info: 'Info',
  }
  return icons[severity] || 'AlertCircle'
}

/**
 * Gibt eine CSS-Klasse für die Severity zurück.
 *
 * @param severity - Der Schweregrad
 * @returns CSS-Klasse
 */
export function getSeverityClass(severity: TranslatedLogMessage['severity']): string {
  const classes: Record<TranslatedLogMessage['severity'], string> = {
    error: 'severity-error',
    warning: 'severity-warning',
    info: 'severity-info',
  }
  return classes[severity] || ''
}

// ============================================================================
// Statistics (für Debugging/Testing)
// ============================================================================

/**
 * Gibt die Anzahl der definierten Pattern zurück.
 */
export function getPatternCount(): number {
  return LOG_PATTERNS.length
}

/**
 * Gibt alle definierten Kategorien zurück.
 */
export function getAllCategories(): LogMessageCategory[] {
  return ['file', 'connection', 'esp', 'validation', 'system', 'auth', 'config', 'database', 'mqtt']
}
