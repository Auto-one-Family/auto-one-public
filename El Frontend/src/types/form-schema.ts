/**
 * Schema-based Form System Type Definitions
 *
 * Used by DynamicForm to render forms from declarative schemas.
 * Supports conditional visibility, validation, and GPIO-specific fields.
 */

export type FieldType = 'text' | 'number' | 'select' | 'toggle' | 'range' | 'gpio-select'

export interface FormFieldSchema {
  /** Unique key used as v-model binding path */
  key: string
  /** Field type determines which input component is rendered */
  type: FieldType
  /** Display label */
  label: string
  /** Placeholder text for text/number inputs */
  placeholder?: string
  /** Helper text shown below the field */
  helper?: string
  /** Whether the field is required */
  required?: boolean
  /** Whether the field is disabled */
  disabled?: boolean

  // Validation constraints
  /** Minimum value (number/range) */
  min?: number
  /** Maximum value (number/range) */
  max?: number
  /** Step increment (number/range) */
  step?: number

  // Select-specific
  /** Options for select fields */
  options?: Array<{ value: string | number; label: string }>

  // Conditional visibility
  /** Show this field only when another field matches a condition */
  dependsOn?: {
    /** Key of the field to watch */
    field: string
    /** Value to compare against */
    value: unknown
    /** Comparison operator (default: '==') */
    operator?: '==' | '!=' | '>' | '<'
  }

  // GPIO-Select-specific
  /** ESP device ID for GPIO availability check */
  espId?: string
}

export interface FormGroupSchema {
  /** Group title */
  title: string
  /** Optional group description */
  description?: string
  /** Whether the group starts collapsed */
  collapsed?: boolean
  /** Fields within this group */
  fields: FormFieldSchema[]
}

export interface FormSchema {
  /** Groups of form fields */
  groups: FormGroupSchema[]
}
