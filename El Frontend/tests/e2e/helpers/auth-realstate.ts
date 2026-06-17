import { spawnSync } from 'node:child_process'
import type { APIRequestContext } from '@playwright/test'

export interface AuthStatusSnapshot {
  setup_required: boolean
  users_exist: boolean
  user_count: number
}

export interface AuthResetResult {
  command: string
  exitCode: number
  durationMs: number
  stdout: string
  stderr: string
}

export interface AuthDataIntegritySnapshot {
  run_id: string
  timestamp: string
  status: AuthStatusSnapshot
}

function resolveFrontendBaseUrl(frontendBaseUrl?: string): string {
  const candidate = frontendBaseUrl || process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:5173'
  return candidate.replace(/\/+$/, '')
}

function resolveApiBaseUrl(frontendBaseUrl?: string): string {
  if (process.env.PLAYWRIGHT_API_BASE) {
    return process.env.PLAYWRIGHT_API_BASE.replace(/\/+$/, '')
  }

  const frontendBase = resolveFrontendBaseUrl(frontendBaseUrl)
  return frontendBase.replace('://localhost:5173', '://localhost:8000')
}

function buildDefaultResetCommand(): string {
  const dockerContainer = process.env.E2E_DB_CONTAINER || 'automationone-postgres'
  const sql = [
    'TRUNCATE TABLE token_blacklist RESTART IDENTITY;',
    'TRUNCATE TABLE user_accounts RESTART IDENTITY CASCADE;',
  ].join(' ')

  return `docker exec ${dockerContainer} sh -lc "psql -U \\"$POSTGRES_USER\\" -d \\"$POSTGRES_DB\\" -c \\"${sql}\\""`.trim()
}

function assertResetTargetIsolation(command: string): void {
  const resetAllowed = process.env.E2E_AUTH_RESET_ALLOWED === 'true'
  const target = (process.env.E2E_AUTH_RESET_TARGET || '').trim()
  const normalizedTarget = target.toLowerCase()
  const isClearlyMarkedTestTarget = /test|e2e|ci|sandbox/.test(normalizedTarget)

  if (!resetAllowed || !target || !isClearlyMarkedTestTarget) {
    throw new Error(
      [
        'Auth-DB-Reset abgebrochen: Test-Isolation nicht eindeutig nachgewiesen.',
        'Erforderlich:',
        '1) E2E_AUTH_RESET_ALLOWED=true',
        '2) E2E_AUTH_RESET_TARGET=<klar markiertes testziel, z. B. automationone_test>',
        '',
        `Aktuell: E2E_AUTH_RESET_ALLOWED=${process.env.E2E_AUTH_RESET_ALLOWED ?? '<unset>'}`,
        `Aktuell: E2E_AUTH_RESET_TARGET=${target || '<unset>'}`,
        `Command: ${command}`,
      ].join('\n')
    )
  }
}

export function resetAuthStateToNoUsers(): AuthResetResult {
  const command = process.env.E2E_AUTH_DB_RESET_CMD?.trim() || buildDefaultResetCommand()
  assertResetTargetIsolation(command)
  const startedAt = Date.now()

  const result = spawnSync(command, {
    shell: true,
    encoding: 'utf-8',
    windowsHide: true,
  })

  const durationMs = Date.now() - startedAt
  const stdout = result.stdout ?? ''
  const stderr = result.stderr ?? ''
  const exitCode = result.status ?? -1

  if (exitCode !== 0) {
    throw new Error(
      [
        `Auth-DB-Reset fehlgeschlagen (exitCode=${exitCode}).`,
        `Command: ${command}`,
        `STDOUT: ${stdout.trim() || '<empty>'}`,
        `STDERR: ${stderr.trim() || '<empty>'}`,
        'Tipp: E2E_AUTH_DB_RESET_CMD setzen, falls dein Reset-Kommando abweicht.',
      ].join('\n')
    )
  }

  return { command, exitCode, durationMs, stdout, stderr }
}

export async function fetchAuthStatusSnapshot(
  request: APIRequestContext,
  frontendBaseUrl?: string
): Promise<AuthStatusSnapshot> {
  const apiBase = resolveApiBaseUrl(frontendBaseUrl)
  const response = await request.get(`${apiBase}/api/v1/auth/status`, {
    timeout: 15000,
  })

  if (!response.ok()) {
    const body = await response.text()
    throw new Error(
      `Auth-Status konnte nicht geladen werden: ${response.status()} ${body || '<empty>'}`
    )
  }

  const data = (await response.json()) as Partial<AuthStatusSnapshot>
  const usersExist = Boolean(data.users_exist)
  const userCount =
    typeof (data as { user_count?: unknown }).user_count === 'number'
      ? ((data as { user_count?: number }).user_count ?? 0)
      : usersExist
        ? 1
        : 0

  return {
    setup_required: Boolean(data.setup_required),
    users_exist: usersExist,
    user_count: userCount,
  }
}

export async function fetchAuthDataIntegritySnapshot(
  request: APIRequestContext,
  runId: string,
  frontendBaseUrl?: string
): Promise<AuthDataIntegritySnapshot> {
  const status = await fetchAuthStatusSnapshot(request, frontendBaseUrl)
  return {
    run_id: runId,
    timestamp: new Date().toISOString(),
    status,
  }
}
