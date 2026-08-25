import { describe, it, expect } from 'vitest'
import {
  doseDriveModeLabel,
  doseMlToDurationSeconds,
  durationSecondsToMlEquivalent,
  isStepDurationReadonly,
  resolveDoseDriveMode,
  resolveStepDoseMode,
  resolveTargetOptimalRuntimeState,
  stepDoseModeHelp,
  stepDoseModeOptionLabel,
  stepEffectiveModeBadgeLabel,
  targetOptimalRuntimeLabel,
} from '@/utils/sequenceDoseDisplay'

describe('sequenceDoseDisplay', () => {
  it('should derive duration from dose_ml / flow_rate', () => {
    expect(doseMlToDurationSeconds(9, 1.5)).toBe(6)
    expect(doseMlToDurationSeconds(9, null)).toBeNull()
  })

  it('should show ml equivalent of seconds × flow_rate', () => {
    expect(durationSecondsToMlEquivalent(5, 1.8)).toBe(9)
    expect(durationSecondsToMlEquivalent(0, 1.8)).toBeNull()
    expect(durationSecondsToMlEquivalent(5, null)).toBeNull()
  })

  it('should resolve ml-driven when dose_ml > 0 (server precedence)', () => {
    expect(resolveDoseDriveMode(9)).toBe('ml_driven')
    expect(resolveDoseDriveMode(undefined)).toBe('duration_driven')
    expect(resolveDoseDriveMode(0)).toBe('duration_driven')
    expect(doseDriveModeLabel('ml_driven')).toBe('ml-getrieben')
    expect(doseDriveModeLabel('duration_driven')).toBe('laufzeit-getrieben')
  })

  it('should resolve step dose_mode flag with legacy fallback', () => {
    expect(resolveStepDoseMode('target_optimal', undefined)).toBe('target_optimal')
    expect(resolveStepDoseMode('ml', 9)).toBe('ml')
    expect(resolveStepDoseMode('duration', 9)).toBe('duration')
    expect(resolveStepDoseMode(undefined, 9)).toBe('ml')
    expect(resolveStepDoseMode(undefined, undefined)).toBe('duration')
  })

  it('should expose human labels and help for three modes', () => {
    expect(stepDoseModeOptionLabel('duration')).toContain('Sekunden')
    expect(stepDoseModeOptionLabel('ml')).toContain('ml')
    expect(stepDoseModeOptionLabel('target_optimal')).toBe('Zielwert-optimal')
    expect(stepDoseModeHelp('target_optimal').length).toBeGreaterThan(20)
  })

  it('should resolve target_optimal runtime matrix by flow_rate then concentration', () => {
    expect(resolveTargetOptimalRuntimeState(null, null)).toBe('duration_fallback')
    expect(resolveTargetOptimalRuntimeState(0, 100)).toBe('duration_fallback')
    expect(resolveTargetOptimalRuntimeState(1.5, null)).toBe('auto_calibrating')
    expect(resolveTargetOptimalRuntimeState(1.5, 0)).toBe('auto_calibrating')
    expect(resolveTargetOptimalRuntimeState(1.5, 80)).toBe('concentration_exact')
    expect(targetOptimalRuntimeLabel('duration_fallback')).toContain('laufzeit-getrieben')
    expect(targetOptimalRuntimeLabel('auto_calibrating')).toContain('Konzentration')
    expect(targetOptimalRuntimeLabel('concentration_exact')).toBe('konzentrations-exakt')
  })

  it('should build effective badge from mode + runtime state', () => {
    expect(stepEffectiveModeBadgeLabel('duration', undefined, null, null)).toBe(
      'laufzeit-getrieben',
    )
    expect(stepEffectiveModeBadgeLabel('ml', 9, 1.5, null)).toBe('ml-getrieben')
    expect(stepEffectiveModeBadgeLabel('target_optimal', 9, null, null)).toContain(
      'laufzeit-getrieben',
    )
    expect(stepEffectiveModeBadgeLabel('target_optimal', 9, 1.5, null)).toContain(
      'Konzentration',
    )
    expect(stepEffectiveModeBadgeLabel('target_optimal', 9, 1.5, 80)).toBe(
      'konzentrations-exakt',
    )
  })

  it('should make duration readonly only when ml path is active', () => {
    expect(isStepDurationReadonly('duration', 9, 1.5)).toBe(false)
    expect(isStepDurationReadonly('ml', 9, 1.5)).toBe(true)
    expect(isStepDurationReadonly('ml', undefined, 1.5)).toBe(false)
    expect(isStepDurationReadonly('target_optimal', 9, null)).toBe(false)
    expect(isStepDurationReadonly('target_optimal', 9, 1.5)).toBe(true)
  })
})
