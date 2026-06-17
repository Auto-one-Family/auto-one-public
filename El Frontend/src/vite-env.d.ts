/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}

interface ImportMetaEnv {
  readonly VITE_API_URL: string
  readonly VITE_LOG_LEVEL: 'error' | 'warn' | 'info' | 'debug'
  /**
   * Optional Google Sheets Spreadsheet-ID (Sheets-Export Pipeline, AUT-450).
   * Wird gesetzt wenn der Server-seitige Sheets-Export aktiv konfiguriert ist
   * (vgl. SHEETS_SPREADSHEET_ID auf dem Server). Read-only UI-Hinweis im
   * Settings-Bereich. Leer/unset => kein UI-Eintrag sichtbar.
   */
  readonly VITE_SHEETS_SPREADSHEET_ID?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
