/**
 * Tests for shared/design primitives barrel exports.
 * Verifies that both Base* names and convenience aliases are exported.
 *
 * Note: Only primitives are tested to avoid transitive dependencies
 * from layout/patterns components that import stores/services.
 */

import { describe, it, expect } from 'vitest'

describe('shared/design primitives exports', () => {
  it('exports all Base* primitives', { timeout: 15000 }, async () => {
    const mod = await import('@/shared/design/primitives')
    expect(mod.BaseCard).toBeDefined()
    expect(mod.BaseBadge).toBeDefined()
    expect(mod.BaseButton).toBeDefined()
    expect(mod.BaseModal).toBeDefined()
    expect(mod.BaseInput).toBeDefined()
    expect(mod.BaseToggle).toBeDefined()
    expect(mod.BaseSelect).toBeDefined()
    expect(mod.BaseSpinner).toBeDefined()
    expect(mod.BaseSkeleton).toBeDefined()
    // New primitives (Dashboard Redesign)
    expect(mod.SlideOver).toBeDefined()
    expect(mod.RangeSlider).toBeDefined()
    expect(mod.QualityIndicator).toBeDefined()
    // Settings-Panel Modernisation (Block B)
    expect(mod.AccordionSection).toBeDefined()
  })

  it('exports convenience aliases for migration', async () => {
    const mod = await import('@/shared/design/primitives')
    expect(mod.Badge).toBeDefined()
    expect(mod.Card).toBeDefined()
    expect(mod.Button).toBeDefined()
    expect(mod.Input).toBeDefined()
    expect(mod.Modal).toBeDefined()
    expect(mod.Select).toBeDefined()
    expect(mod.Toggle).toBeDefined()
    expect(mod.Spinner).toBeDefined()
  })

  it('aliases point to same component as Base* versions', async () => {
    const mod = await import('@/shared/design/primitives')
    expect(mod.Badge).toBe(mod.BaseBadge)
    expect(mod.Card).toBe(mod.BaseCard)
    expect(mod.Button).toBe(mod.BaseButton)
    expect(mod.Input).toBe(mod.BaseInput)
    expect(mod.Modal).toBe(mod.BaseModal)
    expect(mod.Select).toBe(mod.BaseSelect)
    expect(mod.Toggle).toBe(mod.BaseToggle)
    expect(mod.Spinner).toBe(mod.BaseSpinner)
  })

  it('exports 21 named exports (9 Base + 8 aliases + 4 new primitives)', async () => {
    // 9 Base*: BaseCard, BaseBadge, BaseButton, BaseModal, BaseInput, BaseToggle,
    //          BaseSelect, BaseSpinner, BaseSkeleton
    // 8 aliases: Badge, Card, Button, Input, Modal, Select, Toggle, Spinner
    // 4 new: SlideOver, RangeSlider, QualityIndicator, AccordionSection
    const mod = await import('@/shared/design/primitives')
    const exportedKeys = Object.keys(mod)
    expect(exportedKeys.length).toBe(21)
  })
})
