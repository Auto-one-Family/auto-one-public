<script setup lang="ts">
/**
 * SetupView — First-Run Admin Account Creation
 *
 * Visually identical to LoginView (shared aesthetic):
 * - Same ambient particle field + rotating gradients
 * - Logo scanline sweep + breathe glow
 * - Iridescent focus rings with focus-within label glow
 * - Password strength gradient bar (red → yellow → iridescent)
 * - Requirement check spring-bounce micro-animations
 * - Success celebration animation
 * - Staggered entrance sequence
 * - Pure BEM scoped CSS — zero Tailwind utility classes
 */

import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/shared/stores/auth.store'
import { UserPlus, Eye, EyeOff, AlertCircle, CheckCircle, Cpu } from 'lucide-vue-next'

const router = useRouter()
const authStore = useAuthStore()

const username = ref('')
const email = ref('')
const password = ref('')
const confirmPassword = ref('')
const fullName = ref('')
const showPassword = ref(false)
const localError = ref<string | null>(null)
const setupSuccess = ref(false)

const passwordRequirements = computed(() => [
  { met: password.value.length >= 8, text: 'Mindestens 8 Zeichen', key: 'length' },
  { met: /[A-Z]/.test(password.value), text: 'Ein Großbuchstabe', key: 'upper' },
  { met: /[a-z]/.test(password.value), text: 'Ein Kleinbuchstabe', key: 'lower' },
  { met: /[0-9]/.test(password.value), text: 'Eine Zahl', key: 'number' },
  { met: /[!@#$%^&*(),.?":{}|<>]/.test(password.value), text: 'Ein Sonderzeichen', key: 'special' },
])

const passwordValid = computed(() => passwordRequirements.value.every(r => r.met))
const passwordsMatch = computed(() => password.value === confirmPassword.value && confirmPassword.value.length > 0)
const emailValid = computed(() => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.value))
const usernameValid = computed(() => /^[a-zA-Z0-9_]{3,50}$/.test(username.value))

const isValid = computed(() =>
  usernameValid.value &&
  emailValid.value &&
  passwordValid.value &&
  passwordsMatch.value
)

const error = computed(() => localError.value || authStore.error)

// Password strength: 0-5 based on met requirements
const strengthLevel = computed(() => passwordRequirements.value.filter(r => r.met).length)
const strengthPercent = computed(() => (strengthLevel.value / 5) * 100)
const strengthClass = computed(() => {
  if (strengthLevel.value <= 2) return 'setup-strength__bar--weak'
  if (strengthLevel.value <= 4) return 'setup-strength__bar--medium'
  return 'setup-strength__bar--strong'
})

async function handleSetup() {
  if (!isValid.value) return

  localError.value = null

  try {
    await authStore.setup({
      username: username.value,
      email: email.value,
      password: password.value,
      full_name: fullName.value || undefined,
    })

    // Celebration: card animates away before route change
    setupSuccess.value = true
    await new Promise(r => setTimeout(r, 450))

    router.push('/')
  } catch {
    // Error is handled in store
  }
}

// Particle config: identical to LoginView
const particles = Array.from({ length: 18 }, (_, i) => ({
  id: i,
  style: {
    '--dx': `${(Math.random() - 0.5) * 120}px`,
    '--dy': `${(Math.random() - 0.5) * 120}px`,
    '--particle-opacity': `${0.08 + Math.random() * 0.12}`,
    left: `${Math.random() * 100}%`,
    top: `${Math.random() * 100}%`,
    width: `${1.5 + Math.random() * 2}px`,
    height: `${1.5 + Math.random() * 2}px`,
    animationDuration: `${8 + Math.random() * 12}s`,
    animationDelay: `${Math.random() * 8}s`,
  } as Record<string, string>,
}))
</script>

<template>
  <div class="setup-page">
    <!-- Background decoration (identical to LoginView) -->
    <div class="setup-bg">
      <div class="setup-bg__gradient" />
      <div class="setup-bg__grid" />
      <div class="setup-bg__noise" />
      <div class="setup-bg__particles">
        <span
          v-for="p in particles"
          :key="p.id"
          :style="p.style"
        />
      </div>
    </div>

    <div class="setup-container">
      <!-- Logo/Title — stagger entrance 1 -->
      <div class="setup-header setup-entrance setup-entrance--1">
        <div class="setup-logo">
          <Cpu class="setup-logo__icon" />
          <div class="setup-logo__scanline" />
        </div>
        <h1 class="setup-title">Ersteinrichtung</h1>
        <p class="setup-subtitle">Administrator-Konto erstellen</p>
      </div>

      <!-- Setup Card — stagger entrance 2 -->
      <div
        :class="[
          'setup-card',
          'glass-panel',
          'setup-entrance',
          'setup-entrance--2',
          { 'setup-card--success': setupSuccess }
        ]"
      >
        <div class="setup-card__header">
          <h2 class="setup-card__title">Administrator</h2>
          <p class="setup-card__desc">Erster Benutzer mit vollen Rechten</p>
        </div>

        <form @submit.prevent="handleSetup" class="setup-form">
          <!-- Error Message -->
          <div v-if="error" class="setup-error">
            <AlertCircle class="setup-error__icon" />
            <span>{{ error }}</span>
          </div>

          <!-- Username -->
          <div class="setup-form__group">
            <label for="setup-username" class="setup-form__label">Benutzername</label>
            <input
              id="setup-username"
              v-model="username"
              type="text"
              :class="['setup-form__input', { 'setup-form__input--error': username && !usernameValid }]"
              placeholder="admin"
              autocomplete="username"
              required
            />
            <p v-if="username && !usernameValid" class="setup-form__hint setup-form__hint--error">
              3-50 Zeichen, nur Buchstaben, Zahlen und Unterstrich
            </p>
          </div>

          <!-- Email -->
          <div class="setup-form__group">
            <label for="setup-email" class="setup-form__label">E-Mail</label>
            <input
              id="setup-email"
              v-model="email"
              type="email"
              :class="['setup-form__input', { 'setup-form__input--error': email && !emailValid }]"
              placeholder="admin@example.com"
              autocomplete="email"
              required
            />
          </div>

          <!-- Full Name (optional) -->
          <div class="setup-form__group">
            <label for="setup-fullname" class="setup-form__label">
              Vollständiger Name
              <span class="setup-form__label-hint">(optional)</span>
            </label>
            <input
              id="setup-fullname"
              v-model="fullName"
              type="text"
              class="setup-form__input"
              placeholder="Max Mustermann"
              autocomplete="name"
            />
          </div>

          <!-- Password -->
          <div class="setup-form__group">
            <label for="setup-password" class="setup-form__label">Passwort</label>
            <div class="setup-form__password-wrap">
              <input
                id="setup-password"
                v-model="password"
                :type="showPassword ? 'text' : 'password'"
                class="setup-form__input setup-form__input--password"
                placeholder="••••••••"
                autocomplete="new-password"
                required
              />
              <button
                type="button"
                class="setup-form__eye"
                @click="showPassword = !showPassword"
              >
                <Eye v-if="!showPassword" class="setup-form__eye-icon" />
                <EyeOff v-else class="setup-form__eye-icon" />
              </button>
            </div>

            <!-- Password Strength Bar -->
            <div v-if="password.length > 0" class="setup-strength">
              <div
                class="setup-strength__bar"
                :class="strengthClass"
                :style="{ width: strengthPercent + '%' }"
              />
            </div>

            <!-- Password Requirements Grid (2 columns on desktop) -->
            <ul class="setup-requirements">
              <li
                v-for="req in passwordRequirements"
                :key="req.key"
                :class="[
                  'setup-requirements__item',
                  { 'setup-requirements__item--met': req.met }
                ]"
              >
                <CheckCircle v-if="req.met" class="setup-requirements__check" />
                <span v-else class="setup-requirements__dot" />
                <span>{{ req.text }}</span>
              </li>
            </ul>
          </div>

          <!-- Confirm Password -->
          <div class="setup-form__group">
            <label for="setup-confirm" class="setup-form__label">Passwort bestätigen</label>
            <input
              id="setup-confirm"
              v-model="confirmPassword"
              :type="showPassword ? 'text' : 'password'"
              :class="['setup-form__input', { 'setup-form__input--error': confirmPassword && !passwordsMatch }]"
              placeholder="••••••••"
              autocomplete="new-password"
              required
            />
            <p v-if="confirmPassword && !passwordsMatch" class="setup-form__hint setup-form__hint--error">
              Passwörter stimmen nicht überein
            </p>
          </div>

          <!-- Submit -->
          <button
            type="submit"
            class="setup-form__submit btn btn-primary"
            :disabled="!isValid || authStore.isLoading"
          >
            <span v-if="authStore.isLoading" class="setup-form__submit-content">
              <svg class="setup-form__spinner" viewBox="0 0 24 24">
                <circle class="setup-form__spinner-track" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none" />
                <path class="setup-form__spinner-head" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              Konto wird erstellt...
            </span>
            <span v-else class="setup-form__submit-content">
              <UserPlus class="setup-form__submit-icon" />
              Administrator erstellen
            </span>
          </button>
        </form>
      </div>

      <!-- Footer — stagger entrance 3 -->
      <footer class="setup-footer setup-entrance setup-entrance--3">
        AutomationOne · Ersteinrichtung
      </footer>
    </div>
  </div>
</template>

<style scoped>
/* ═══════════════════════════════════════════════════════════════════════════
   SETUP PAGE — First-Run Account Creation
   Identical aesthetic to LoginView. Pure BEM, no Tailwind utilities.
   ═══════════════════════════════════════════════════════════════════════════ */

.setup-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-4);
  background-color: var(--color-bg-primary);
  position: relative;
  overflow: hidden;
}

/* ── Background (identical to LoginView) ── */
.setup-bg {
  position: absolute;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
}

.setup-bg__gradient {
  position: absolute;
  top: -50%;
  left: -50%;
  width: 200%;
  height: 200%;
  background:
    radial-gradient(circle at 30% 30%, rgba(96, 165, 250, 0.08) 0%, transparent 50%),
    radial-gradient(circle at 70% 70%, rgba(167, 139, 250, 0.08) 0%, transparent 50%),
    radial-gradient(circle at 50% 80%, rgba(96, 165, 250, 0.04) 0%, transparent 40%);
  animation: rotate 60s linear infinite;
}

@keyframes rotate {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.setup-bg__grid {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.02) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.02) 1px, transparent 1px);
  background-size: 40px 40px;
}

.setup-bg__noise {
  position: absolute;
  inset: 0;
  opacity: 0.02;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E");
  pointer-events: none;
}

.setup-bg__particles {
  position: absolute;
  inset: 0;
}

.setup-bg__particles span {
  position: absolute;
  border-radius: var(--radius-full);
  background: var(--color-iridescent-1);
  animation: particle-drift linear infinite;
}

/* ── Staggered Entrance ── */
.setup-entrance {
  opacity: 0;
}

.setup-entrance--1 {
  animation: slide-down 0.45s var(--ease-out) 0.1s both;
}

.setup-entrance--2 {
  animation: slide-up 0.45s var(--ease-out) 0.2s both;
}

.setup-entrance--3 {
  animation: fade-in 0.4s var(--ease-out) 0.4s both;
}

/* ── Container ── */
.setup-container {
  width: 100%;
  max-width: 28rem; /* slightly wider than login for more fields */
  position: relative;
  z-index: var(--z-dropdown);
}

/* ── Header ── */
.setup-header {
  text-align: center;
  margin-bottom: var(--space-8);
}

.setup-logo {
  width: 4rem;
  height: 4rem;
  margin: 0 auto var(--space-4);
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-lg);
  background: linear-gradient(135deg, var(--color-iridescent-1), var(--color-iridescent-3));
  color: white;
  position: relative;
  overflow: hidden;
  animation: logo-breathe 5s var(--ease-in-out) infinite;
}

.setup-logo__icon {
  width: 2.5rem;
  height: 2.5rem;
  position: relative;
  z-index: var(--z-dropdown);
}

.setup-logo__scanline {
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: linear-gradient(
    180deg,
    transparent 0%,
    rgba(255, 255, 255, 0.1) 48%,
    rgba(255, 255, 255, 0.25) 50%,
    rgba(255, 255, 255, 0.1) 52%,
    transparent 100%
  );
  animation: scanline 4s var(--ease-in-out) infinite;
  pointer-events: none;
}

.setup-title {
  font-size: var(--text-display);
  font-weight: 700;
  letter-spacing: var(--tracking-tight);
  background: linear-gradient(135deg, var(--color-iridescent-1), var(--color-iridescent-3));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.setup-subtitle {
  color: var(--color-text-muted);
  font-size: var(--text-sm);
  letter-spacing: var(--tracking-wide);
  text-transform: uppercase;
  margin-top: var(--space-1);
}

/* ── Card ── */
.setup-card {
  border-radius: var(--radius-lg);
  overflow: hidden;
  transition: transform 0.5s var(--ease-out), opacity 0.5s var(--ease-out), filter 0.5s var(--ease-out);
}

.setup-card--success {
  animation: login-success 0.5s var(--ease-out) forwards;
  pointer-events: none;
}

.setup-card__header {
  padding: var(--space-6) var(--space-6) 0;
}

.setup-card__title {
  font-size: var(--text-xl);
  font-weight: 600;
  color: var(--color-text-primary);
}

.setup-card__desc {
  font-size: var(--text-sm);
  color: var(--color-text-muted);
  margin-top: var(--space-1);
}

/* ── Form ── */
.setup-form {
  padding: var(--space-6);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.setup-form__group {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

/* Industrial HUD labels — glow on focus-within */
.setup-form__label {
  font-size: var(--text-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
  color: var(--color-text-muted);
  transition: color var(--transition-fast);
}

.setup-form__label-hint {
  font-weight: 400;
  text-transform: none;
  letter-spacing: 0;
  opacity: 0.6;
}

.setup-form__group:focus-within .setup-form__label {
  color: var(--color-iridescent-1);
}

/* Inputs with depth + iridescent focus */
.setup-form__input {
  width: 100%;
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-md);
  background-color: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  color: var(--color-text-primary);
  font-family: var(--font-body);
  font-size: var(--text-base);
  box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.25);
  outline: none;
  transition:
    border-color var(--transition-fast),
    box-shadow var(--transition-base),
    background-color var(--transition-base);
}

.setup-form__input::placeholder {
  color: var(--color-text-muted);
}

.setup-form__input:focus {
  border-color: var(--color-iridescent-2);
  background-color: rgba(21, 21, 31, 0.8);
  box-shadow:
    inset 0 2px 4px rgba(0, 0, 0, 0.2),
    0 0 0 2px var(--color-bg-primary),
    0 0 0 4px rgba(129, 140, 248, 0.3),
    0 0 16px rgba(96, 165, 250, 0.08);
}

.setup-form__input--error {
  border-color: var(--color-error);
}

.setup-form__input--error:focus {
  box-shadow:
    inset 0 2px 4px rgba(0, 0, 0, 0.2),
    0 0 0 2px var(--color-bg-primary),
    0 0 0 4px rgba(248, 113, 113, 0.2);
}

/* Password wrapper */
.setup-form__password-wrap {
  position: relative;
}

.setup-form__input--password {
  padding-right: 3rem;
}

.setup-form__eye {
  position: absolute;
  right: var(--space-3);
  top: 50%;
  transform: translateY(-50%);
  padding: var(--space-1);
  color: var(--color-text-muted);
  background: none;
  border: none;
  cursor: pointer;
  transition: color var(--transition-fast);
}

.setup-form__eye:hover {
  color: var(--color-text-primary);
}

.setup-form__eye-icon {
  width: 20px;
  height: 20px;
}

/* Validation hint text */
.setup-form__hint {
  font-size: var(--text-xs);
  margin-top: var(--space-1);
}

.setup-form__hint--error {
  color: var(--color-error);
}

/* ── Password Strength Bar ── */
.setup-strength {
  height: 3px;
  background: var(--color-bg-quaternary);
  border-radius: var(--radius-full);
  margin-top: var(--space-2);
  overflow: hidden;
}

.setup-strength__bar {
  height: 100%;
  border-radius: inherit;
  transition: width var(--transition-base), background var(--transition-base);
}

.setup-strength__bar--weak {
  background: var(--color-error);
}

.setup-strength__bar--medium {
  background: var(--color-warning);
}

.setup-strength__bar--strong {
  background: var(--gradient-iridescent);
}

/* ── Password Requirements Grid ── */
.setup-requirements {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-1) var(--space-4);
  margin-top: var(--space-2);
  list-style: none;
  padding: 0;
}

.setup-requirements__item {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  transition: color var(--transition-base), transform var(--transition-base);
}

.setup-requirements__item--met {
  color: var(--color-success);
  animation: requirement-check 0.3s var(--ease-spring);
}

.setup-requirements__check {
  width: 12px;
  height: 12px;
  flex-shrink: 0;
}

.setup-requirements__dot {
  width: 12px;
  height: 12px;
  flex-shrink: 0;
  border-radius: var(--radius-full);
  border: 1px solid var(--color-text-muted);
  opacity: 0.5;
}

/* Responsive: single column on small screens */
@media (max-width: 480px) {
  .setup-requirements {
    grid-template-columns: 1fr;
  }
}

/* ── Error ── */
.setup-error {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3);
  background-color: rgba(248, 113, 113, 0.1);
  border: 1px solid rgba(248, 113, 113, 0.2);
  border-radius: var(--radius-md);
  color: var(--color-error);
  font-size: var(--text-sm);
  animation: slide-down 0.25s var(--ease-out);
}

.setup-error__icon {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
}

/* ── Submit ── */
.setup-form__submit {
  width: 100%;
}

.setup-form__submit-content {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
}

.setup-form__submit-icon {
  width: 20px;
  height: 20px;
}

.setup-form__spinner {
  width: 20px;
  height: 20px;
  animation: spin 0.8s linear infinite;
}

.setup-form__spinner-track {
  opacity: 0.25;
}

.setup-form__spinner-head {
  opacity: 0.75;
}

/* ── Footer ── */
.setup-footer {
  text-align: center;
  color: var(--color-text-muted);
  font-size: var(--text-xs);
  letter-spacing: var(--tracking-wide);
  margin-top: var(--space-6);
}

/* ── Reduced Motion ── */
@media (prefers-reduced-motion: reduce) {
  .setup-entrance--1,
  .setup-entrance--2,
  .setup-entrance--3 {
    animation: none;
    opacity: 1;
  }

  .setup-logo {
    animation: none;
  }

  .setup-logo__scanline {
    animation: none;
    display: none;
  }

  .setup-bg__gradient {
    animation: none;
  }

  .setup-bg__particles span {
    animation: none;
    display: none;
  }

  .setup-card--success {
    animation: none;
    opacity: 0;
  }

  .setup-requirements__item--met {
    animation: none;
  }
}
</style>
