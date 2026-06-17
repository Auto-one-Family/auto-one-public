const MAX_DECODE_ATTEMPTS = 2

function tryDecodeURIComponent(value: string): string {
  try {
    return decodeURIComponent(value)
  } catch {
    return value
  }
}

function decodeRedirectValue(rawValue: string): string {
  let current = rawValue
  for (let attempt = 0; attempt < MAX_DECODE_ATTEMPTS; attempt++) {
    const decoded = tryDecodeURIComponent(current)
    if (decoded === current) {
      break
    }
    current = decoded
  }
  return current
}

function isSafeInternalPath(path: string): boolean {
  // Strictly allow app-internal absolute paths only.
  if (!path.startsWith('/')) {
    return false
  }
  // Disallow protocol-relative and backslash variants.
  if (path.startsWith('//') || path.startsWith('/\\')) {
    return false
  }
  return true
}

/**
 * Redirect contract for post-login navigation:
 * - Semantic target restoration has priority over URL string encoding form.
 * - Raw and encoded redirect query forms are normalized to an internal path.
 * - Unsafe values fall back to the provided default route.
 */
export function resolvePostLoginRedirect(rawRedirect: unknown, fallbackPath = '/'): string {
  if (typeof rawRedirect !== 'string' || rawRedirect.length === 0) {
    return fallbackPath
  }

  const normalizedPath = decodeRedirectValue(rawRedirect.trim())
  if (!isSafeInternalPath(normalizedPath)) {
    return fallbackPath
  }

  return normalizedPath
}
