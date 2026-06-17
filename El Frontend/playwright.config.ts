import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright E2E + CSS Test Configuration
 *
 * Purpose: Browser-based E2E tests AND comprehensive CSS/visual testing
 *          for AutomationOne Vue 3 Dashboard
 * Architecture: Playwright on HOST, backend services in Docker
 *
 * Usage:
 *   make e2e-up                                  # Start Docker services
 *   npx playwright test                          # Run all tests
 *   npx playwright test --project=chromium       # Chromium only (fast)
 *   npx playwright test tests/e2e/css/           # CSS tests only
 *   npx playwright test tests/e2e/scenarios/     # E2E scenario tests only
 *   npx playwright test --ui                     # Interactive UI mode
 *   npx playwright test --debug                  # Debug mode
 *   npx playwright test --update-snapshots       # Update visual baselines
 *   make e2e-down                                # Stop Docker services
 *
 * Auth Flow:
 *   globalSetup logs in once, saves token to .playwright/auth-state.json
 *   All tests reuse this auth state (storageState)
 *
 * CSS Test Architecture (5 layers):
 *   1. Design Token Verification   — tokens.css values correct
 *   2. CSS Property Assertions     — computed styles match spec
 *   3. Responsive Layout Tests     — multi-viewport layout checks
 *   4. Accessibility & Contrast    — axe-core + WCAG 2.1 AA
 *   5. Visual Regression           — screenshot baselines
 */

export default defineConfig({
  // Test directories — both scenarios and CSS tests
  testDir: './tests/e2e',

  // Test file pattern
  testMatch: '**/*.spec.ts',

  // Exclude visual-regression tests in CI: no baseline screenshots available.
  // Visual regression requires pre-committed baselines (npx playwright test --update-snapshots).
  // Run locally only: npx playwright test tests/e2e/css/visual-regression.spec.ts
  testIgnore: process.env.CI ? ['**/visual-regression.spec.ts'] : [],

  // Run tests in parallel (but scenarios within a file run sequentially)
  fullyParallel: true,

  // Fail the build on CI if test.only is left in
  forbidOnly: !!process.env.CI,

  // Retry on CI only (flaky test recovery)
  retries: process.env.CI ? 1 : 0,

  // Limit parallel workers on CI (resource constraints)
  workers: process.env.CI ? 2 : undefined,

  // Reporter configuration
  reporter: [
    ['html', { outputFolder: './playwright-report', open: 'never' }],
    ['list'],
    ...(process.env.CI ? [['github' as const]] : []),
  ],

  // Global setup/teardown for auth
  globalSetup: './tests/e2e/global-setup.ts',
  globalTeardown: './tests/e2e/global-teardown.ts',

  // Shared settings for all projects
  use: {
    // Base URL for all page.goto() calls
    baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:5173',

    // Reuse auth state from global setup
    storageState: '.playwright/auth-state.json',

    // Collect trace on first retry (debugging)
    trace: 'on-first-retry',

    // Screenshot on failure
    screenshot: 'only-on-failure',

    // Video on first retry
    video: 'on-first-retry',

    // Viewport size (desktop default)
    viewport: { width: 1280, height: 720 },

    // Longer timeout for WebSocket-based tests
    actionTimeout: 10000,
    navigationTimeout: 30000,
  },

  // Global test timeout
  timeout: 30000,

  // Expect timeout + screenshot defaults
  expect: {
    timeout: 10000,
    toHaveScreenshot: {
      // Allow 1% pixel difference (font rendering varies)
      maxDiffPixelRatio: 0.01,
      // Disable animations for stable screenshots
      animations: 'disabled',
    },
  },

  // Snapshot path template — organized by project and test file
  snapshotPathTemplate: '{testDir}/__screenshots__/{projectName}/{testFilePath}/{arg}{ext}',

  // Output directory for artifacts
  outputDir: './test-results',

  // ═══════════════════════════════════════════════════════════════════════
  // PROJECTS — Multi-browser + Multi-viewport
  // ═══════════════════════════════════════════════════════════════════════
  projects: [
    // ── Desktop Browsers ──
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    },

    // ── Mobile Viewports ──
    {
      name: 'mobile-chrome',
      use: {
        ...devices['Pixel 7'],
      },
    },
    {
      name: 'mobile-safari',
      use: {
        ...devices['iPhone 14'],
      },
    },

    // ── Tablet Viewport ──
    {
      name: 'tablet',
      use: {
        ...devices['iPad (gen 7)'],
      },
    },
  ],

  // Web server is managed externally via Docker
  // No webServer config needed - we use make e2e-up
})
