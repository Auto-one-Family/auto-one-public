<script setup lang="ts">
/**
 * LoginView — Addictive Auth Experience
 *
 * Mission Control login with:
 * - Ambient particle field (CSS-only, no dependencies)
 * - Logo scanline sweep + breathe glow
 * - Iridescent focus rings with depth shift
 * - focus-within label glow
 * - Success celebration animation before route change
 * - Live server telemetry footer
 * - Staggered entrance sequence
 */

import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/shared/stores/auth.store'
import { useWebSocket } from '@/composables/useWebSocket'
import { resolvePostLoginRedirect } from '@/utils/redirectContract'
import { LogIn, Eye, EyeOff, AlertCircle, Cpu, Check } from 'lucide-vue-next'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

// WebSocket for footer status (auto-connect, no filters needed)
const { isConnected, connectionStatus } = useWebSocket({ autoConnect: true })

// Server health info for footer telemetry
const serverHealth = ref<{ status: string; devices: number; uptime: string } | null>(null)

onMounted(async () => {
  try {
    const res = await fetch('/health')
    if (res.ok) {
      const data = await res.json()
      const uptimeSec = data.uptime_seconds ?? 0
      const hours = Math.floor(uptimeSec / 3600)
      const minutes = Math.floor((uptimeSec % 3600) / 60)
      serverHealth.value = {
        status: data.status ?? 'unknown',
        devices: data.connected_devices ?? data.mqtt_connected_devices ?? 0,
        uptime: hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`,
      }
    }
  } catch {
    // Health endpoint unavailable — footer stays minimal
  }
})

const username = ref('')
const password = ref('')
const rememberMe = ref(false)
const showPassword = ref(false)
const localError = ref<string | null>(null)
const loginSuccess = ref(false)

const isValid = computed(() => username.value.length >= 3 && password.value.length >= 8)
const error = computed(() => localError.value || authStore.error)

// Connection dot class reused from TopBar pattern
const connectionDotClass = computed(() => {
  switch (connectionStatus.value) {
    case 'connected': return 'login-footer__dot--connected'
    case 'connecting': return 'login-footer__dot--connecting'
    case 'error': return 'login-footer__dot--error'
    default: return 'login-footer__dot--disconnected'
  }
})

const footerStatusText = computed(() => {
  if (!authStore.accessToken) return 'Anmeldung erforderlich'
  if (isConnected.value) return 'God-Kaiser Server'
  if (connectionStatus.value === 'connecting') return 'Verbinde...'
  return 'Server getrennt'
})

async function handleLogin() {
  if (!isValid.value) return

  localError.value = null

  try {
    await authStore.login({
      username: username.value,
      password: password.value,
      remember_me: rememberMe.value,
    })

    // Celebration: card animates away before route change
    loginSuccess.value = true
    await new Promise(r => setTimeout(r, 450))

    const targetPath = resolvePostLoginRedirect(route.query.redirect, '/')
    router.push(targetPath)
  } catch {
    // Error is handled in store
  }
}

// Particle config: 18 ambient particles with randomized CSS custom properties
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
  <div class="login-page">
    <!-- Background decoration -->
    <div class="login-bg">
      <div class="login-bg-gradient" />
      <div class="login-bg-grid" />
      <div class="login-bg-noise" />
      <!-- Ambient particles -->
      <div class="login-bg-particles">
        <span
          v-for="p in particles"
          :key="p.id"
          :style="p.style"
        />
      </div>
    </div>

    <div class="login-container">
      <!-- Logo/Title — stagger entrance 1 -->
      <div class="login-header login-entrance login-entrance--1">
        <div class="login-logo">
          <Cpu class="login-logo__icon" />
          <div class="login-logo__scanline" />
        </div>
        <h1 class="login-title">AutomationOne</h1>
        <p class="login-subtitle">Steuerungszentrale</p>
      </div>

      <!-- Login Card — stagger entrance 2 -->
      <div
        :class="[
          'login-card',
          'glass-panel',
          'login-entrance',
          'login-entrance--2',
          { 'login-card--success': loginSuccess }
        ]"
      >
        <div class="login-card__header">
          <h2 class="login-card__title">Anmelden</h2>
          <p class="login-card__desc">Zugangsdaten eingeben</p>
        </div>

        <form @submit.prevent="handleLogin" class="login-form">
          <!-- Error Message -->
          <div v-if="error" class="login-error">
            <AlertCircle class="login-error__icon" />
            <span>{{ error }}</span>
          </div>

          <!-- Username -->
          <div class="login-form__group">
            <label for="username" class="login-form__label">Benutzername</label>
            <input
              id="username"
              v-model="username"
              type="text"
              class="login-form__input"
              placeholder="admin"
              autocomplete="username"
              required
            />
          </div>

          <!-- Password -->
          <div class="login-form__group">
            <label for="password" class="login-form__label">Passwort</label>
            <div class="login-form__password-wrap">
              <input
                id="password"
                v-model="password"
                :type="showPassword ? 'text' : 'password'"
                class="login-form__input login-form__input--password"
                placeholder="••••••••"
                autocomplete="current-password"
                required
              />
              <button
                type="button"
                class="login-form__eye"
                @click="showPassword = !showPassword"
              >
                <Eye v-if="!showPassword" class="login-form__eye-icon" />
                <EyeOff v-else class="login-form__eye-icon" />
              </button>
            </div>
          </div>

          <!-- Remember Me -->
          <label for="remember" class="login-form__row login-form__checkbox-wrap">
            <input
              id="remember"
              v-model="rememberMe"
              type="checkbox"
              class="login-form__checkbox-input"
            />
            <span class="login-form__checkbox-box" aria-hidden="true">
              <Check class="login-form__checkbox-icon" />
            </span>
            <span class="login-form__checkbox-label">Angemeldet bleiben (7 Tage)</span>
          </label>

          <!-- Submit -->
          <button
            type="submit"
            class="login-form__submit btn btn-primary"
            :disabled="!isValid || authStore.isLoading"
          >
            <span v-if="authStore.isLoading" class="login-form__submit-content">
              <svg class="login-form__spinner" viewBox="0 0 24 24">
                <circle class="login-form__spinner-track" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none" />
                <path class="login-form__spinner-head" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              Wird angemeldet...
            </span>
            <span v-else class="login-form__submit-content">
              <LogIn class="login-form__submit-icon" />
              Anmelden
            </span>
          </button>
        </form>
      </div>

      <!-- Footer — stagger entrance 3 -->
      <footer class="login-footer login-entrance login-entrance--3">
        <span class="login-footer__dot" :class="connectionDotClass" />
        <span class="login-footer__status">
          {{ footerStatusText }}
        </span>
        <template v-if="isConnected && serverHealth">
          <span class="login-footer__sep">·</span>
          <span class="login-footer__detail">{{ serverHealth.devices }} Geräte</span>
          <span class="login-footer__sep">·</span>
          <span class="login-footer__detail">Uptime {{ serverHealth.uptime }}</span>
        </template>
      </footer>
    </div>
  </div>
</template>

<style scoped>
/* ═══════════════════════════════════════════════════════════════════════════
   LOGIN PAGE — Addictive Auth Experience
   Token-aligned, BEM, no Tailwind utilities. Scoped to this view only.
   ═══════════════════════════════════════════════════════════════════════════ */

.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-4);
  background-color: var(--color-bg-primary);
  position: relative;
  overflow: hidden;
}

/* ── Background Layers ── */
.login-bg {
  position: absolute;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
}

.login-bg-gradient {
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

.login-bg-grid {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.02) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.02) 1px, transparent 1px);
  background-size: 40px 40px;
}

.login-bg-noise {
  position: absolute;
  inset: 0;
  opacity: 0.02;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E");
  pointer-events: none;
}

/* ── Ambient Particles ── */
.login-bg-particles {
  position: absolute;
  inset: 0;
}

.login-bg-particles span {
  position: absolute;
  border-radius: var(--radius-full);
  background: var(--color-iridescent-1);
  animation: particle-drift linear infinite;
}

/* ── Staggered Entrance ── */
.login-entrance {
  opacity: 0;
}

.login-entrance--1 {
  animation: slide-down 0.45s var(--ease-out) 0.1s both;
}

.login-entrance--2 {
  animation: slide-up 0.45s var(--ease-out) 0.2s both;
}

.login-entrance--3 {
  animation: fade-in 0.4s var(--ease-out) 0.4s both;
}

/* ── Container ── */
.login-container {
  width: 100%;
  max-width: 24rem;
  position: relative;
  z-index: var(--z-dropdown);
}

/* ── Header ── */
.login-header {
  text-align: center;
  margin-bottom: var(--space-8);
}

/* Logo with scanline + breathe */
.login-logo {
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

.login-logo__icon {
  width: 2.5rem;
  height: 2.5rem;
  position: relative;
  z-index: var(--z-dropdown);
}

.login-logo__scanline {
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

.login-title {
  font-size: var(--text-display);
  font-weight: 700;
  letter-spacing: var(--tracking-tight);
  background: linear-gradient(135deg, var(--color-iridescent-1), var(--color-iridescent-3));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.login-subtitle {
  color: var(--color-text-muted);
  font-size: var(--text-sm);
  letter-spacing: var(--tracking-wide);
  text-transform: uppercase;
  margin-top: var(--space-1);
}

/* ── Card ── */
.login-card {
  border-radius: var(--radius-lg);
  overflow: hidden;
  transition: transform 0.5s var(--ease-out), opacity 0.5s var(--ease-out), filter 0.5s var(--ease-out);
}

.login-card--success {
  animation: login-success 0.5s var(--ease-out) forwards;
  pointer-events: none;
}

.login-card__header {
  padding: var(--space-6) var(--space-6) 0;
}

.login-card__title {
  font-size: var(--text-xl);
  font-weight: 600;
  color: var(--color-text-primary);
}

.login-card__desc {
  font-size: var(--text-sm);
  color: var(--color-text-muted);
  margin-top: var(--space-1);
}

/* ── Form ── */
.login-form {
  padding: var(--space-6);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.login-form__group {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

/* Industrial HUD labels — glow on focus-within */
.login-form__label {
  font-size: var(--text-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
  color: var(--color-text-secondary);
  transition: color var(--transition-fast);
}

.login-form__group:focus-within .login-form__label {
  color: var(--color-iridescent-1);
}

/* Inputs with depth + iridescent focus */
.login-form__input {
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

.login-form__input::placeholder {
  color: var(--color-text-muted);
}

.login-form__input:focus {
  border-color: var(--color-iridescent-2);
  background-color: rgba(21, 21, 31, 0.8);
  box-shadow:
    inset 0 2px 4px rgba(0, 0, 0, 0.2),
    0 0 0 2px var(--color-bg-primary),
    0 0 0 4px rgba(129, 140, 248, 0.3),
    0 0 16px rgba(96, 165, 250, 0.08);
}

/* Password wrapper */
.login-form__password-wrap {
  position: relative;
}

.login-form__input--password {
  padding-right: 3rem;
}

.login-form__eye {
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

.login-form__eye:hover {
  color: var(--color-text-primary);
}

.login-form__eye-icon {
  width: 20px;
  height: 20px;
}

/* Checkbox row */
.login-form__row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.login-form__checkbox-wrap {
  min-height: 44px;
  cursor: pointer;
  user-select: none;
}

.login-form__checkbox-input {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

.login-form__checkbox-box {
  width: 1.125rem;
  height: 1.125rem;
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
  background-color: var(--color-bg-tertiary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition:
    border-color var(--transition-fast),
    background-color var(--transition-fast),
    box-shadow var(--transition-fast),
    transform var(--transition-fast);
  box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.25);
}

.login-form__checkbox-icon {
  width: 0.75rem;
  height: 0.75rem;
  color: var(--color-bg-primary);
  opacity: 0;
  transform: scale(0.8);
  transition: opacity var(--transition-fast), transform var(--transition-fast);
}

.login-form__checkbox-wrap:hover .login-form__checkbox-box {
  border-color: rgba(129, 140, 248, 0.7);
}

.login-form__checkbox-input:focus-visible + .login-form__checkbox-box {
  border-color: var(--color-iridescent-2);
  box-shadow:
    0 0 0 2px var(--color-bg-primary),
    0 0 0 4px rgba(129, 140, 248, 0.32),
    0 0 12px rgba(96, 165, 250, 0.18);
}

.login-form__checkbox-input:checked + .login-form__checkbox-box {
  border-color: var(--color-iridescent-2);
  background: linear-gradient(135deg, var(--color-iridescent-1), var(--color-iridescent-3));
}

.login-form__checkbox-input:checked + .login-form__checkbox-box .login-form__checkbox-icon {
  opacity: 1;
  transform: scale(1);
}

.login-form__checkbox-label {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  cursor: pointer;
}

/* Submit button */
.login-form__submit {
  width: 100%;
}

.login-form__submit-content {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
}

.login-form__submit-icon {
  width: 20px;
  height: 20px;
}

.login-form__spinner {
  width: 20px;
  height: 20px;
  animation: spin 0.8s linear infinite;
}

.login-form__spinner-track {
  opacity: 0.25;
}

.login-form__spinner-head {
  opacity: 0.75;
}

/* ── Error ── */
.login-error {
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

.login-error__icon {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
}

/* ── Footer: Live Telemetry ── */
.login-footer {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  margin-top: var(--space-6);
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  letter-spacing: var(--tracking-wide);
}

.login-footer__dot {
  width: 6px;
  height: 6px;
  border-radius: var(--radius-full);
  flex-shrink: 0;
  transition: background-color var(--transition-base), box-shadow var(--transition-base);
}

.login-footer__dot--connected {
  background-color: var(--color-success);
  box-shadow: 0 0 6px rgba(52, 211, 153, 0.5);
  animation: pulse-dot 3s ease-in-out infinite;
}

.login-footer__dot--connecting {
  background-color: var(--color-warning);
  box-shadow: 0 0 6px rgba(251, 191, 36, 0.4);
  animation: pulse-dot 1.2s ease-in-out infinite;
}

.login-footer__dot--error {
  background-color: var(--color-error);
  box-shadow: 0 0 6px rgba(248, 113, 113, 0.4);
}

.login-footer__dot--disconnected {
  background-color: var(--color-text-muted);
}

.login-footer__status {
  font-weight: 500;
}

.login-footer__sep {
  opacity: 0.4;
}

.login-footer__detail {
  font-variant-numeric: tabular-nums;
  opacity: 0.7;
}

/* ── Reduced Motion ── */
@media (prefers-reduced-motion: reduce) {
  .login-entrance--1,
  .login-entrance--2,
  .login-entrance--3 {
    animation: none;
    opacity: 1;
  }

  .login-logo {
    animation: none;
  }

  .login-logo__scanline {
    animation: none;
    display: none;
  }

  .login-bg-gradient {
    animation: none;
  }

  .login-bg-particles span {
    animation: none;
    display: none;
  }

  .login-card--success {
    animation: none;
    opacity: 0;
  }
}
</style>
