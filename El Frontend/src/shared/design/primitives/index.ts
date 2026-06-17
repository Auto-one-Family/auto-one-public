/**
 * Design System Primitives
 *
 * Base UI components - the atomic building blocks of the design system.
 * All component names use the Base* prefix to indicate they are primitives.
 */

export { default as BaseCard } from './BaseCard.vue'
export { default as BaseBadge } from './BaseBadge.vue'
export { default as BaseButton } from './BaseButton.vue'
export { default as BaseModal } from './BaseModal.vue'
export { default as BaseInput } from './BaseInput.vue'
export { default as BaseToggle } from './BaseToggle.vue'
export { default as BaseSelect } from './BaseSelect.vue'
export { default as BaseSpinner } from './BaseSpinner.vue'
export { default as BaseSkeleton } from './BaseSkeleton.vue'

// Convenience aliases (migration from components/common)
export { default as Badge } from './BaseBadge.vue'
export { default as Card } from './BaseCard.vue'
export { default as Button } from './BaseButton.vue'
export { default as Input } from './BaseInput.vue'
export { default as Modal } from './BaseModal.vue'
export { default as Select } from './BaseSelect.vue'
export { default as Toggle } from './BaseToggle.vue'
export { default as Spinner } from './BaseSpinner.vue'

// New primitives (Dashboard Redesign)
export { default as SlideOver } from './SlideOver.vue'
export { default as RangeSlider } from './RangeSlider.vue'
export { default as QualityIndicator } from './QualityIndicator.vue'
export { default as AccordionSection } from './AccordionSection.vue'
