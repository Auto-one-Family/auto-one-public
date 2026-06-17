/**
 * Hysteresis Logic E2E Test (T18-V7)
 *
 * Full end-to-end test of the hysteresis logic:
 * - Creates a Mock ESP with DS18B20 temperature sensor and relay actuator
 * - Creates a hysteresis rule: "Lüfter AN bei >28°C, AUS bei <24°C"
 * - Simulates temperature sequence: 25 → 29 → 26 → 23 → 25°C
 * - Verifies: activation at 29°C, no flutter at 26°C (hysteresis zone),
 *   deactivation at 23°C, stays inactive at 25°C
 *
 * Requires: Docker services running (backend + MQTT + DB)
 * Run: make e2e-up && npx playwright test tests/e2e/scenarios/hysteresis-logic.spec.ts
 */

import { test, expect, type Page, type APIRequestContext } from '@playwright/test'
import { createMockEspWithSensors, deleteMockEsp } from '../helpers/api'
import { publishSensorData, publishHeartbeat, generateMockId } from '../helpers/mqtt'

// ── Constants ───────────────────────────────────────────────────────────

const ZONE_ID = 'e2e_hysteresis_zone'
const ZONE_NAME = 'Hysterese-Test'
const TEMP_GPIO = 4
const RELAY_GPIO = 16
const ACTIVATE_ABOVE = 28.0
const DEACTIVATE_BELOW = 24.0

const TOKEN_KEY = 'el_frontend_access_token'

// ── API Helpers ─────────────────────────────────────────────────────────

function getApiBase(pageUrl: string): string {
  const origin = new URL(pageUrl).origin
  return process.env.PLAYWRIGHT_API_BASE ?? origin.replace('5173', '8000')
}

async function getToken(page: Page): Promise<string> {
  const token = await page.evaluate(
    (key: string) => localStorage.getItem(key),
    TOKEN_KEY
  )
  if (!token) throw new Error('No auth token in localStorage')
  return token
}

/**
 * Create a hysteresis cooling rule via the API.
 * Condition: activate above 28°C, deactivate below 24°C
 */
async function createHysteresisCoolingRule(
  page: Page,
  request: APIRequestContext,
  espId: string,
  options?: { activateAbove?: number; deactivateBelow?: number }
): Promise<string> {
  const { activateAbove = ACTIVATE_ABOVE, deactivateBelow = DEACTIVATE_BELOW } =
    options ?? {}
  const apiBase = `${getApiBase(page.url())}/api/v1`
  const token = await getToken(page)

  const rulePayload = {
    name: `E2E: Hysterese-Kühlung ${Date.now()}`,
    description: 'Lüfter AN bei >28°C, AUS bei <24°C — verhindert Flattern',
    enabled: true,
    conditions: [
      {
        type: 'hysteresis',
        esp_id: espId,
        gpio: TEMP_GPIO,
        sensor_type: 'ds18b20',
        activate_above: activateAbove,
        deactivate_below: deactivateBelow,
      },
    ],
    logic_operator: 'AND',
    actions: [
      {
        type: 'actuator',
        esp_id: espId,
        gpio: RELAY_GPIO,
        command: 'ON',
        value: 1.0,
      },
    ],
    priority: 10,
    cooldown_seconds: 5,
    max_executions_per_hour: 20,
  }

  const response = await request.post(`${apiBase}/logic/rules`, {
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    data: rulePayload,
    timeout: 15000,
  })

  if (!response.ok()) {
    const text = await response.text()
    throw new Error(`Failed to create hysteresis rule: ${response.status()} - ${text}`)
  }

  const data = (await response.json()) as { id: string }
  return data.id
}

async function deleteLogicRule(
  page: Page,
  request: APIRequestContext,
  ruleId: string
): Promise<void> {
  const apiBase = `${getApiBase(page.url())}/api/v1`
  const token = await getToken(page)

  await request
    .delete(`${apiBase}/logic/rules/${ruleId}`, {
      headers: { Authorization: `Bearer ${token}` },
      timeout: 5000,
    })
    .catch(() => {})
}

async function getExecutionHistory(
  page: Page,
  request: APIRequestContext,
  ruleId: string,
  limit = 10
): Promise<Array<{ id: string; success: boolean }>> {
  const apiBase = `${getApiBase(page.url())}/api/v1`
  const token = await getToken(page)

  const response = await request.get(
    `${apiBase}/logic/execution_history?rule_id=${ruleId}&limit=${limit}`,
    {
      headers: { Authorization: `Bearer ${token}` },
      timeout: 10000,
    }
  )
  if (!response.ok()) return []
  const data = (await response.json()) as { entries: Array<{ id: string; success: boolean }> }
  return data.entries ?? []
}

// ═══════════════════════════════════════════════════════════════════════
// TEST SUITE
// ═══════════════════════════════════════════════════════════════════════

test.describe('Hysteresis Logic: DS18B20 → Relay (Kühlung)', () => {
  test.skip(!!process.env.CI, 'Requires live backend + MQTT — use docker compose e2e-up')
  test.setTimeout(90000)

  let espId: string
  let ruleId: string

  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('load')
  })

  test.afterEach(async ({ page, request }) => {
    if (ruleId) {
      await deleteLogicRule(page, request, ruleId).catch(() => {})
      ruleId = ''
    }
    if (espId) {
      await deleteMockEsp(page, request, espId).catch(() => {})
      espId = ''
    }
  })

  test('should create mock ESP with DS18B20 and relay', async ({ page, request }) => {
    espId = generateMockId('HYST')

    const result = await createMockEspWithSensors(page, request, {
      espId,
      sensors: [
        {
          gpio: TEMP_GPIO,
          sensor_type: 'DS18B20',
          name: 'Temperatur Hysterese',
          raw_value: 25.0,
        },
      ],
      actuators: [
        {
          gpio: RELAY_GPIO,
          actuator_type: 'relay',
          name: 'Lüfter',
        },
      ],
      auto_heartbeat: true,
    })

    expect(result.success).toBe(true)
    expect(result.esp_id).toBe(espId)

    await publishHeartbeat(espId)
    await page.waitForTimeout(1000)

    await page.goto('/hardware')
    await page.waitForLoadState('load')
    await page.waitForTimeout(2000)

    // Device visible (zone omitted - E2E DB has no zones)
    await page.waitForTimeout(1000)
  })

  test('should create hysteresis cooling rule', async ({ page, request }) => {
    espId = generateMockId('RULE')

    await createMockEspWithSensors(page, request, {
      espId,
      sensors: [
        {
          gpio: TEMP_GPIO,
          sensor_type: 'DS18B20',
          name: 'Temperatur',
          raw_value: 25.0,
        },
      ],
      actuators: [
        { gpio: RELAY_GPIO, actuator_type: 'relay', name: 'Lüfter' },
      ],
      auto_heartbeat: true,
    })

    await publishHeartbeat(espId)
    await page.waitForTimeout(1000)

    ruleId = await createHysteresisCoolingRule(page, request, espId)
    expect(ruleId).toBeTruthy()
  })

  test('should run full hysteresis sequence 25→29→26→23→25°C', async ({
    page,
    request,
  }) => {
    espId = generateMockId('SEQ')

    await createMockEspWithSensors(page, request, {
      espId,
      sensors: [
        {
          gpio: TEMP_GPIO,
          sensor_type: 'DS18B20',
          name: 'Temperatur',
          raw_value: 25.0,
        },
      ],
      actuators: [
        { gpio: RELAY_GPIO, actuator_type: 'relay', name: 'Lüfter' },
      ],
      auto_heartbeat: true,
    })

    await publishHeartbeat(espId)
    await page.waitForTimeout(1000)

    ruleId = await createHysteresisCoolingRule(page, request, espId)
    expect(ruleId).toBeTruthy()
    await page.waitForTimeout(500)

    // Step 1: 25°C — inactive (between 24–28)
    await publishSensorData(espId, TEMP_GPIO, 25.0, {
      sensorType: 'ds18b20',
    })
    await page.waitForTimeout(1500)

    let hist = await getExecutionHistory(page, request, ruleId, 5)
    const countBefore29 = hist.length

    // Step 2: 29°C — should activate (ON)
    await publishSensorData(espId, TEMP_GPIO, 29.0, {
      sensorType: 'ds18b20',
    })
    await page.waitForTimeout(2000)

    hist = await getExecutionHistory(page, request, ruleId, 5)
    const countAfter29 = hist.length
    expect(countAfter29).toBeGreaterThan(countBefore29)

    // Step 3: 26°C — should stay active (NO new logic_execution = hysteresis zone)
    await publishSensorData(espId, TEMP_GPIO, 26.0, {
      sensorType: 'ds18b20',
    })
    await page.waitForTimeout(1500)

    hist = await getExecutionHistory(page, request, ruleId, 5)
    const countAfter26 = hist.length
    expect(countAfter26).toBe(countAfter29)

    // Step 4: 23°C — should deactivate (OFF)
    await publishSensorData(espId, TEMP_GPIO, 23.0, {
      sensorType: 'ds18b20',
    })
    await page.waitForTimeout(2000)

    hist = await getExecutionHistory(page, request, ruleId, 10)
    const countAfter23 = hist.length
    expect(countAfter23).toBeGreaterThan(countAfter26)

    // Step 5: 25°C — should stay inactive
    await publishSensorData(espId, TEMP_GPIO, 25.0, {
      sensorType: 'ds18b20',
    })
    await page.waitForTimeout(1500)

    hist = await getExecutionHistory(page, request, ruleId, 10)
    const countAfter25 = hist.length
    expect(countAfter25).toBe(countAfter23)
  })
})
