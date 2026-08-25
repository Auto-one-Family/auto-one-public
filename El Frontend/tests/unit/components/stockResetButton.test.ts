import { describe, it, expect } from 'vitest'
import {
  canShowStockResetButton,
  buildStockResetConfirmMessage,
} from '@/components/plants/stockResetButton'

describe('canShowStockResetButton', () => {
  it('should show for part_b with pump and recipe', () => {
    expect(
      canShowStockResetButton({
        doseRole: 'part_b',
        hasPump: true,
        recipeId: 'a1361361-0000-4000-8000-000000000002',
      }),
    ).toBe(true)
  })

  it('should hide for ph_down', () => {
    expect(
      canShowStockResetButton({
        doseRole: 'ph_down',
        hasPump: true,
        recipeId: 'abc',
      }),
    ).toBe(false)
  })

  it('should hide without pump or recipe', () => {
    expect(
      canShowStockResetButton({
        doseRole: 'part_a',
        hasPump: false,
        recipeId: 'abc',
      }),
    ).toBe(false)
    expect(
      canShowStockResetButton({
        doseRole: 'part_a',
        hasPump: true,
        recipeId: null,
      }),
    ).toBe(false)
  })
})

describe('buildStockResetConfirmMessage', () => {
  it('should mention recipe and remeasure without inventing a schedule', () => {
    const { title, message } = buildStockResetConfirmMessage({
      doseRole: 'part_b',
      recipeLabel: 'Übergang 8-6-12 Teil B',
    })
    expect(title).toContain('Stock B')
    expect(message).toContain('Übergang 8-6-12 Teil B')
    expect(message).toContain('nächsten Dosierlauf')
    expect(message).not.toMatch(/\d+\s*Minuten|\d+\s*Stunden/)
  })
})
