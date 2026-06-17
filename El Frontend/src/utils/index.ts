/**
 * Utils Index
 *
 * Central export point for all utility functions and configurations.
 */

// Sensor configuration and defaults
export * from './sensorDefaults'

// Human-readable labels (German)
export * from './labels'

// Formatting utilities
export * from './formatters'

// Error code translation (German)
export * from './errorCodeTranslator'

// Database column translation (German)
export * from './databaseColumnTranslator'

// Log message translation (German)
export * from './logMessageTranslator'

// WiFi signal strength utilities
export * from './wifiStrength'

// Zone color utilities
export * from './zoneColors'

// Actuator defaults
export * from './actuatorDefaults'

// Subzone helpers (normalize "Keine Subzone" for API, German slug)
export { normalizeSubzoneId, slugifyGerman } from './subzoneHelpers'

// Logger utility
export { createLogger } from './logger'
export type { Logger } from './logger'

// NOTE: gpioConfig is NOT exported here due to naming conflict
// (getCategoryLabel exists in both gpioConfig and errorCodeTranslator)
// Import directly: import { ... } from '@/utils/gpioConfig'







