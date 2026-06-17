/**
 * MSW Server Setup
 *
 * Creates the MSW server for Node.js environment (Vitest).
 * This server intercepts HTTP requests during tests.
 */

import { setupServer } from 'msw/node'
import { handlers } from './handlers'

// Create MSW server with all handlers
export const server = setupServer(...handlers)

// Re-export handlers for test-specific overrides
export { handlers }
