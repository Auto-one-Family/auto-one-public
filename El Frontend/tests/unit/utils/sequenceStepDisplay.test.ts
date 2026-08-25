/**
 * AUT-1306 C5: Sequenz-Node-Gesicht Format Nr · Typ · Primär · Detail
 */
import { describe, it, expect } from 'vitest'
import {
  sequenceStepNumber,
  sequenceStepTypeLabel,
  sequenceStepPrimaryLabel,
  sequenceStepDetailLabel,
  formatSequenceStepFaceLine,
} from '@/utils/sequenceStepDisplay'
import type { SequenceStepDraft } from '@/types/logic'

const formatDuration = (s: number) => `${s} s`
const resolveName = (espId?: string, gpio?: number, fallback?: string) =>
  fallback || (espId && gpio != null ? `${espId}:GPIO${gpio}` : 'Nicht konfiguriert')

describe('sequenceStepDisplay', () => {
  it('should number all steps 1-based including pauses', () => {
    expect(sequenceStepNumber(0)).toBe('1')
    expect(sequenceStepNumber(3)).toBe('4')
  })

  it('should label step types as Aktor and Pause', () => {
    expect(sequenceStepTypeLabel('actuator')).toBe('Aktor')
    expect(sequenceStepTypeLabel('delay')).toBe('Pause')
  })

  it('should default pause primary label to Pause not Mischzeit', () => {
    const pause: SequenceStepDraft = { stepType: 'delay', seconds: 30 }
    expect(sequenceStepPrimaryLabel(pause, resolveName)).toBe('Pause')
    expect(sequenceStepPrimaryLabel({ ...pause, name: 'Mischzeit' }, resolveName)).toBe('Mischzeit')
  })

  it('should show dose detail with mode label (AUT-1379) and pause duration', () => {
    const dose: SequenceStepDraft = {
      stepType: 'actuator',
      dose_ml: 9,
      duration: 5,
      command: 'ON',
    }
    expect(sequenceStepDetailLabel(dose, formatDuration)).toBe('9 ml (ml-getrieben)')
    expect(sequenceStepDetailLabel({ stepType: 'delay', seconds: 45 }, formatDuration)).toBe('45 s')
    expect(
      sequenceStepDetailLabel(
        { stepType: 'actuator', duration: 5, command: 'ON' },
        formatDuration,
      ),
    ).toBe('5 s (laufzeit-getrieben)')
  })

  it('should show Zielwert-optimal on node face when dose_mode is set (AUT-1390)', () => {
    expect(
      sequenceStepDetailLabel(
        {
          stepType: 'actuator',
          dose_mode: 'target_optimal',
          duration: 5,
          command: 'ON',
        },
        formatDuration,
      ),
    ).toBe('5 s (Zielwert-optimal)')
    expect(
      sequenceStepDetailLabel(
        {
          stepType: 'actuator',
          dose_mode: 'target_optimal',
          dose_ml: 9,
          duration: 5,
          command: 'ON',
        },
        formatDuration,
      ),
    ).toBe('9 ml (Zielwert-optimal)')
  })

  it('should format face line as Nr · Typ · Primär · Detail', () => {
    const steps: SequenceStepDraft[] = [
      { stepType: 'actuator', name: 'Pumpe A', dose_ml: 9, command: 'ON' },
      { stepType: 'delay', seconds: 60 },
      { stepType: 'actuator', name: 'Pumpe B', duration: 5, command: 'ON' },
      {
        stepType: 'actuator',
        name: 'Pump B',
        dose_mode: 'target_optimal',
        duration: 5,
        command: 'ON',
      },
    ]
    expect(formatSequenceStepFaceLine(steps[0], 0, resolveName, formatDuration)).toBe(
      '1 · Aktor · Pumpe A · 9 ml (ml-getrieben)',
    )
    expect(formatSequenceStepFaceLine(steps[1], 1, resolveName, formatDuration)).toBe(
      '2 · Pause · Pause · 60 s',
    )
    expect(formatSequenceStepFaceLine(steps[2], 2, resolveName, formatDuration)).toBe(
      '3 · Aktor · Pumpe B · 5 s (laufzeit-getrieben)',
    )
    expect(formatSequenceStepFaceLine(steps[3], 3, resolveName, formatDuration)).toBe(
      '4 · Aktor · Pump B · 5 s (Zielwert-optimal)',
    )
  })
})

