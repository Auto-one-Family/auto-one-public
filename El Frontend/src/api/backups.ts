/**
 * Database Backup API Client
 *
 * Frontend client for PostgreSQL backup management endpoints.
 * Backend: El Servador/god_kaiser_server/src/api/v1/backups.py
 *
 * Endpoints:
 *   POST   /v1/backups/database/create        - Trigger immediate backup
 *   GET    /v1/backups/database/list           - List all backups
 *   GET    /v1/backups/database/{id}/download  - Download backup file
 *   DELETE /v1/backups/database/{id}           - Delete single backup
 *   POST   /v1/backups/database/{id}/restore   - Restore from backup
 *   POST   /v1/backups/database/cleanup        - Cleanup old backups
 */

import api from './index'

// =============================================================================
// Types
// =============================================================================

export interface DatabaseBackupInfo {
  backup_id: string
  filename: string
  created_at: string
  size_bytes: number
  size_human: string
  pg_version: string | null
  database: string | null
  duration_seconds: number | null
}

export interface DatabaseBackupListResponse {
  status: string
  count: number
  backups: DatabaseBackupInfo[]
}

export interface DatabaseBackupCreateResponse {
  status: string
  message: string
  backup: DatabaseBackupInfo
}

export interface DatabaseBackupDeleteResponse {
  status: string
  message: string
  backup_id: string
}

export interface DatabaseBackupRestoreResponse {
  status: string
  message: string
  backup_id: string
  filename: string
  duration_seconds: number
}

export interface DatabaseBackupCleanupResponse {
  status: string
  deleted_by_age: number
  deleted_by_count: number
  total_deleted: number
  remaining: number
}

// =============================================================================
// API Client
// =============================================================================

export const backupsApi = {
  /**
   * Create an immediate database backup (admin only)
   */
  async createBackup(): Promise<DatabaseBackupCreateResponse> {
    const response = await api.post<DatabaseBackupCreateResponse>(
      '/backups/database/create'
    )
    return response.data
  },

  /**
   * List all available database backups (admin only)
   */
  async listBackups(): Promise<DatabaseBackupListResponse> {
    const response = await api.get<DatabaseBackupListResponse>(
      '/backups/database/list'
    )
    return response.data
  },

  /**
   * Get download URL for a specific backup
   */
  getDownloadUrl(backupId: string): string {
    return `${api.defaults.baseURL}/backups/database/${backupId}/download`
  },

  /**
   * Delete a specific backup (admin only)
   */
  async deleteBackup(backupId: string): Promise<DatabaseBackupDeleteResponse> {
    const response = await api.delete<DatabaseBackupDeleteResponse>(
      `/backups/database/${backupId}`
    )
    return response.data
  },

  /**
   * Restore database from a backup (admin only, requires confirmation)
   * WARNING: This replaces ALL current data!
   */
  async restoreBackup(backupId: string): Promise<DatabaseBackupRestoreResponse> {
    const response = await api.post<DatabaseBackupRestoreResponse>(
      `/backups/database/${backupId}/restore?confirm=true`
    )
    return response.data
  },

  /**
   * Cleanup old backups based on retention policy (admin only)
   */
  async cleanupBackups(): Promise<DatabaseBackupCleanupResponse> {
    const response = await api.post<DatabaseBackupCleanupResponse>(
      '/backups/database/cleanup'
    )
    return response.data
  },
}
