/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        dark: {
          50: 'var(--color-text-inverse)',
          100: 'var(--color-text-primary)',
          200: 'var(--color-text-primary)',
          300: 'var(--color-text-secondary)',
          400: 'var(--color-text-muted)',
          500: 'var(--color-text-secondary)',
          600: 'var(--color-text-secondary)',
          700: 'var(--color-bg-hover)',
          800: 'var(--color-bg-tertiary)',
          900: 'var(--color-bg-secondary)',
          950: 'var(--color-bg-primary)',
        },
        iridescent: {
          1: 'var(--color-iridescent-1)',
          2: 'var(--color-iridescent-2)',
          3: 'var(--color-iridescent-3)',
          4: 'var(--color-iridescent-4)',
          DEFAULT: 'var(--color-iridescent-1)',
        },
        success: {
          DEFAULT: 'var(--color-success)',
          light: 'var(--color-success-bg)',
          dark: 'color-mix(in srgb, var(--color-success) 75%, black)',
        },
        warning: {
          DEFAULT: 'var(--color-warning)',
          light: 'var(--color-warning-bg)',
          dark: 'color-mix(in srgb, var(--color-warning) 75%, black)',
        },
        danger: {
          DEFAULT: 'var(--color-error)',
          light: 'var(--color-error-bg)',
          dark: 'color-mix(in srgb, var(--color-error) 75%, black)',
        },
        info: {
          DEFAULT: 'var(--color-info)',
          light: 'var(--color-info-bg)',
          dark: 'color-mix(in srgb, var(--color-info) 75%, black)',
        },
        mock: {
          DEFAULT: 'var(--color-mock)',
          light: 'color-mix(in srgb, var(--color-mock) 12%, transparent)',
          border: 'color-mix(in srgb, var(--color-mock) 25%, transparent)',
        },
        real: {
          DEFAULT: 'var(--color-real)',
          light: 'color-mix(in srgb, var(--color-real) 12%, transparent)',
          border: 'color-mix(in srgb, var(--color-real) 25%, transparent)',
        },
        esp: {
          online: 'var(--color-status-good)',
          offline: 'var(--color-status-offline)',
          error: 'var(--color-status-alarm)',
          safe: 'var(--color-status-warning)',
        },
        accent: {
          DEFAULT: 'var(--color-accent)',
          bright: 'var(--color-accent-bright)',
          dim: 'var(--color-accent-dim)',
        },
        glass: {
          bg: 'var(--glass-bg)',
          border: 'var(--glass-border)',
        },
      },

      fontFamily: {
        sans: ['Outfit', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },

      fontSize: {
        'xs':      ['0.6875rem', { lineHeight: '1.25' }],
        'sm':      ['0.75rem',   { lineHeight: '1.35' }],
        'base':    ['0.875rem',  { lineHeight: '1.5' }],
        'lg':      ['1rem',      { lineHeight: '1.5' }],
        'xl':      ['1.25rem',   { lineHeight: '1.35' }],
        '2xl':     ['1.5rem',    { lineHeight: '1.25' }],
        'display': ['2rem',      { lineHeight: '1.2' }],
      },

      animation: {
        'shimmer': 'shimmer 4s infinite',
        'pulse-slow': 'pulse-glow 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'skeleton': 'skeleton-loading 1.5s infinite',
        'pulse-dot': 'pulse-dot 2s infinite',
        'glow-line': 'glow-line 2s ease-in-out infinite',
        'fade-in': 'fade-in 0.3s ease-out forwards',
        'slide-up': 'slide-up 0.35s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        'slide-down': 'slide-down 0.35s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        'scale-in': 'scale-in 0.2s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        'blink-error': 'blink-error 1.2s ease-in-out infinite',
        'breathe': 'breathe 3s ease-in-out infinite',
        'value-flash': 'value-flash 0.4s ease-out',
        'zoom-in-exit':  'zoom-in-exit 0.25s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        'zoom-in-enter': 'zoom-in-enter 0.3s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        'zoom-out-exit':  'zoom-out-exit 0.25s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        'zoom-out-enter': 'zoom-out-enter 0.3s cubic-bezier(0.16, 1, 0.3, 1) forwards',
      },

      keyframes: {
        shimmer: {
          '0%': { left: '-100%' },
          '100%': { left: '200%' },
        },
        'skeleton-loading': {
          '0%': { backgroundPosition: '200% 0' },
          '100%': { backgroundPosition: '-200% 0' },
        },
        'pulse-dot': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.4' },
        },
        'pulse-glow': {
          '0%, 100%': { opacity: '1', boxShadow: '0 0 4px currentColor' },
          '50%': { opacity: '0.6', boxShadow: '0 0 12px currentColor' },
        },
        'glow-line': {
          '0%, 100%': { opacity: '0.6', boxShadow: '0 0 4px currentColor' },
          '50%': { opacity: '1', boxShadow: '0 0 8px currentColor' },
        },
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        'slide-up': {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'slide-down': {
          '0%': { opacity: '0', transform: 'translateY(-8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'scale-in': {
          '0%': { opacity: '0', transform: 'scale(0.95)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
        'blink-error': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.3' },
        },
        'breathe': {
          '0%, 100%': { opacity: '0.6', transform: 'scale(1)' },
          '50%': { opacity: '1', transform: 'scale(1.05)' },
        },
        'value-flash': {
          '0%': { backgroundColor: 'color-mix(in srgb, var(--color-info) 15%, transparent)' },
          '100%': { backgroundColor: 'transparent' },
        },
        'zoom-in-exit': {
          '0%':   { opacity: '1', transform: 'scale(1)' },
          '100%': { opacity: '0', transform: 'scale(1.08)' },
        },
        'zoom-in-enter': {
          '0%':   { opacity: '0', transform: 'scale(0.92)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
        'zoom-out-exit': {
          '0%':   { opacity: '1', transform: 'scale(1)' },
          '100%': { opacity: '0', transform: 'scale(0.92)' },
        },
        'zoom-out-enter': {
          '0%':   { opacity: '0', transform: 'scale(1.08)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
      },

      boxShadow: {
        'glass': 'var(--glass-shadow)',
        'card-hover': '0 4px 20px color-mix(in srgb, var(--color-info) 8%, transparent)',
        'iridescent': '0 4px 20px color-mix(in srgb, var(--color-iridescent-1) 15%, transparent)',
        'raised': 'var(--elevation-raised)',
        'floating': 'var(--elevation-floating)',
      },

      backdropBlur: {
        'glass': '12px',
      },

      borderRadius: {
        'sm': '6px',
        'md': '10px',
        'lg': '16px',
        'xl': '16px',
        '2xl': '16px',
      },

      screens: {
        // AUT-49 audit: 3xl/4xl remain available for explicit widescreen-only layouts.
        // Standard responsive work should prefer default Tailwind breakpoints up to 2xl.
        '3xl': '1600px',
        '4xl': '1920px',
      },

      spacing: {
        '0.75': '0.1875rem',
        '1.25': '0.3125rem',
        '3.5':  '0.875rem',
        '4.5':  '1.125rem',
        '13':   '3.25rem',
        '15':   '3.75rem',
      },
    },
  },
  plugins: [],
}
