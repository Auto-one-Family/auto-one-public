/**
 * Playwright Global Teardown
 *
 * Runs after all tests complete.
 * Currently minimal - auth state is intentionally kept for faster re-runs.
 */

import { FullConfig } from '@playwright/test'

async function globalTeardown(config: FullConfig): Promise<void> {
  console.log('[Global Teardown] E2E tests completed')

  // Note: We intentionally keep .playwright/auth-state.json
  // This allows faster test re-runs without re-authenticating
  // The global-setup checks token expiration anyway

  // If cleanup is needed, uncomment:
  // const authStatePath = path.join(__dirname, '../../.playwright/auth-state.json')
  // if (fs.existsSync(authStatePath)) {
  //   fs.unlinkSync(authStatePath)
  // }
}

export default globalTeardown
