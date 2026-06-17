#include "watchdog_storage.h"

#ifndef NATIVE_TEST

#include "../services/config/storage_manager.h"
#include "../models/watchdog_types.h"
#include "../utils/logger.h"
#include <Arduino.h>
#include <ArduinoJson.h>
#include <esp_system.h>
#include <atomic>
#include <string.h>
#include <time.h>

static const char* TAG = "WDT_NVS";

static const char* kNamespace = "wdt_diag";
static const char* kHistKey = "hist";
static const char* kSnapKey = "snap";

// Rolling window: store at most this many epoch seconds (comma-separated)
static constexpr uint8_t kMaxHistEntries = 24;
static constexpr uint32_t kMinValidEpoch = 1700000000UL;  // ~2023 — distinguishes real time from unset
static constexpr uint32_t kSecondsPerDay = 86400UL;

static bool s_boot_was_wdt = false;
static bool s_finalize_done = false;
static std::atomic<uint32_t> s_hist_not_found_expected_count{0};
static std::atomic<uint32_t> s_hist_not_found_unexpected_count{0};
static uint32_t s_last_expected_log_ms = 0;
static uint32_t s_last_unexpected_log_ms = 0;

static constexpr uint32_t kExpectedNotFoundLogIntervalMs = 300000UL;   // 5 min
static constexpr uint32_t kUnexpectedNotFoundLogIntervalMs = 60000UL;  // 60 s

static bool openNs(bool read_only) {
  return storageManager.beginNamespace(kNamespace, read_only);
}

static void closeNs() {
  storageManager.endNamespace();
}

static uint8_t countEntriesInWindow(const char* hist, time_t now) {
  if (!hist || hist[0] == '\0' || now < (time_t)kMinValidEpoch) {
    return 0;
  }
  uint8_t n = 0;
  char buf[256];
  strncpy(buf, hist, sizeof(buf) - 1);
  buf[sizeof(buf) - 1] = '\0';

  char* saveptr = nullptr;
  char* token = strtok_r(buf, ",", &saveptr);
  while (token != nullptr) {
    unsigned long ts = strtoul(token, nullptr, 10);
    if (ts >= kMinValidEpoch && (time_t)ts >= now - (time_t)kSecondsPerDay) {
      n++;
    }
    token = strtok_r(nullptr, ",", &saveptr);
  }
  return n;
}

static String pruneAndAppend(const char* hist, uint32_t new_ts, time_t now) {
  if (now < (time_t)kMinValidEpoch) {
    return String(hist ? hist : "");
  }

  uint32_t cutoff = (uint32_t)(now - (time_t)kSecondsPerDay);
  String out;
  if (hist && hist[0] != '\0') {
    char buf[256];
    strncpy(buf, hist, sizeof(buf) - 1);
    buf[sizeof(buf) - 1] = '\0';
    char* saveptr = nullptr;
    char* tok = strtok_r(buf, ",", &saveptr);
    while (tok != nullptr) {
      unsigned long ts = strtoul(tok, nullptr, 10);
      if (ts >= kMinValidEpoch && ts >= cutoff) {
        if (out.length() > 0) {
          out += ',';
        }
        out += String((uint32_t)ts);
      }
      tok = strtok_r(nullptr, ",", &saveptr);
    }
  }

  if (new_ts >= kMinValidEpoch && (time_t)new_ts >= now - (time_t)kSecondsPerDay) {
    if (out.length() > 0) {
      out += ',';
    }
    out += String(new_ts);
  }

  while (out.length() > 220) {
    int comma = out.indexOf(',');
    if (comma < 0) {
      break;
    }
    out = out.substring(comma + 1);
  }

  (void)kMaxHistEntries;
  return out;
}

void watchdogStorageInitEarly() {
  s_finalize_done = false;
  s_boot_was_wdt = (esp_reset_reason() == ESP_RST_TASK_WDT);

  // Ensure namespace exists early to avoid periodic read-only NOT_FOUND noise
  // from watchdogStorageGetCountLast24h() when diagnostics snapshots run.
  if (openNs(false)) {
    closeNs();
  }
}

void watchdogStorageTryFinalizeBootRecord() {
  if (s_finalize_done) {
    return;
  }
  if (!s_boot_was_wdt) {
    s_finalize_done = true;
    return;
  }

  time_t now = time(nullptr);
  if (now < (time_t)kMinValidEpoch) {
    return;
  }

  if (!openNs(false)) {
    LOG_W(TAG, "watchdogStorageTryFinalizeBootRecord: NVS open failed");
    return;
  }

  const char* prev = storageManager.getString(kHistKey, "");
  String updated = pruneAndAppend(prev, (uint32_t)now, now);
  bool ok = storageManager.putString(kHistKey, updated.c_str());
  closeNs();

  if (!ok) {
    LOG_W(TAG, "watchdogStorageTryFinalizeBootRecord: failed to persist history");
    return;
  }

  s_boot_was_wdt = false;
  s_finalize_done = true;

  uint8_t c = watchdogStorageGetCountLast24h();
  if (c >= 3) {
    LOG_C(TAG, "3× Watchdog in 24h (recorded) — threshold reached (policy: see system state)");
  }
}

uint8_t watchdogStorageGetCountLast24h() {
  time_t now = time(nullptr);
  if (!openNs(true)) {
    return 0;
  }
  if (!storageManager.keyExists(kHistKey)) {
    uint32_t now_ms = millis();
    bool unexpected_missing =
        s_boot_was_wdt && s_finalize_done && now >= (time_t)kMinValidEpoch;

    if (unexpected_missing) {
      uint32_t c = s_hist_not_found_unexpected_count.fetch_add(1) + 1;
      if (now_ms - s_last_unexpected_log_ms >= kUnexpectedNotFoundLogIntervalMs) {
        s_last_unexpected_log_ms = now_ms;
        LOG_W(TAG, "watchdog_history_missing class=unexpected_missing_key count=" + String(c));
      }
    } else {
      uint32_t c = s_hist_not_found_expected_count.fetch_add(1) + 1;
      if (now_ms - s_last_expected_log_ms >= kExpectedNotFoundLogIntervalMs) {
        s_last_expected_log_ms = now_ms;
        LOG_D(TAG, "watchdog_history_missing class=expected_not_found count=" + String(c));
      }
    }
    closeNs();
    return 0;
  }

  const char* hist = storageManager.getString(kHistKey, "");
  uint8_t n = countEntriesInWindow(hist, now);
  closeNs();
  return n;
}

uint32_t watchdogStorageGetHistNotFoundExpectedCount() {
  return s_hist_not_found_expected_count.load();
}

uint32_t watchdogStorageGetHistNotFoundUnexpectedCount() {
  return s_hist_not_found_unexpected_count.load();
}

void watchdogStorageSaveDiagnosticsSnapshot(const WatchdogDiagnostics& diag) {
  DynamicJsonDocument doc(384);
  doc["lc"] = diag.last_feed_component ? diag.last_feed_component : "";
  doc["st"] = static_cast<int>(diag.system_state);
  doc["wf"] = static_cast<int>(diag.wifi_breaker_state);
  doc["mf"] = static_cast<int>(diag.mqtt_breaker_state);
  doc["ec"] = diag.error_count;
  doc["hf"] = diag.heap_free;
  doc["ts"] = (uint32_t)time(nullptr);

  String payload;
  if (serializeJson(doc, payload) == 0) {
    return;
  }
  if (!openNs(false)) {
    return;
  }
  storageManager.putString(kSnapKey, payload.c_str());
  closeNs();
}

void watchdogStorageLogLastSnapshotIfAny() {
  if (esp_reset_reason() != ESP_RST_TASK_WDT) {
    return;
  }
  if (!openNs(true)) {
    return;
  }
  const char* raw = storageManager.getString(kSnapKey, "");
  if (raw == nullptr || raw[0] == '\0') {
    closeNs();
    return;
  }

  DynamicJsonDocument doc(384);
  DeserializationError err = deserializeJson(doc, raw);
  closeNs();

  if (err) {
    LOG_W(TAG, "Last WDT snapshot: parse error");
    return;
  }

  LOG_W(TAG, "Last WDT snapshot (pre-reset): feed=" + String(doc["lc"].as<const char*>()) +
               " state=" + String(doc["st"].as<int>()) + " heap=" + String(doc["hf"].as<uint32_t>()));
}

#endif  // NATIVE_TEST
