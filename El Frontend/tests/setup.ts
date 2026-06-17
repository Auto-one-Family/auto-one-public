/**
 * Vitest Global Setup
 *
 * Mocks for browser APIs not available in happy-dom,
 * and common test infrastructure.
 */

import { vi } from 'vitest'
import { config } from '@vue/test-utils'

// Mock ResizeObserver (not available in happy-dom)
globalThis.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver

// Mock canvas context for Chart.js
HTMLCanvasElement.prototype.getContext = (() => ({
  canvas: { width: 300, height: 150 },
  clearRect: vi.fn(),
  beginPath: vi.fn(),
  moveTo: vi.fn(),
  lineTo: vi.fn(),
  stroke: vi.fn(),
  fill: vi.fn(),
  arc: vi.fn(),
  closePath: vi.fn(),
  fillRect: vi.fn(),
  strokeRect: vi.fn(),
  measureText: vi.fn(() => ({ width: 0 })),
  setTransform: vi.fn(),
  resetTransform: vi.fn(),
  scale: vi.fn(),
  translate: vi.fn(),
  rotate: vi.fn(),
  save: vi.fn(),
  restore: vi.fn(),
  createLinearGradient: vi.fn(() => ({ addColorStop: vi.fn() })),
  createRadialGradient: vi.fn(() => ({ addColorStop: vi.fn() })),
  clip: vi.fn(),
  drawImage: vi.fn(),
  getImageData: vi.fn(() => ({ data: new Uint8ClampedArray(0) })),
  putImageData: vi.fn(),
  createPattern: vi.fn(),
  fillText: vi.fn(),
  strokeText: vi.fn(),
  setLineDash: vi.fn(),
  getLineDash: vi.fn(() => []),
  isPointInPath: vi.fn(),
  isPointInStroke: vi.fn(),
})) as unknown as typeof HTMLCanvasElement.prototype.getContext

// Create a stub component factory for lucide icons
function createIconStub(name: string) {
  return { name, render: () => null }
}

// Stub all lucide-vue-next icons dynamically via Proxy
// Any icon import (e.g. Settings2, Heart) auto-generates a stub component
vi.mock('lucide-vue-next', () => {
  const cache: Record<string, unknown> = {}
  return new Proxy(cache, {
    get(target, prop: string) {
      if (prop === '__esModule') return true
      if (prop === 'default') return target
      if (!target[prop]) {
        target[prop] = createIconStub(prop)
      }
      return target[prop]
    },
  })
})

// Global stubs for Teleport to prevent DOM issues
config.global.stubs = {
  Teleport: true,
}
