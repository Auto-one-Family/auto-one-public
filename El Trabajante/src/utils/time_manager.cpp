/**
 * @file time_manager.cpp
 * @brief NTP Time Synchronization Manager Implementation
 * 
 * Industrial-grade NTP synchronization for ESP32 IoT applications.
 * 
 * Implementation Notes:
 * - Uses configTime() for initial NTP configuration
 * - getLocalTime() retrieves synchronized time
 * - Fallback to estimated time if sync fails
 * - Thread-safe for FreeRTOS multi-task environments
 * 
 * @version 1.0.0
 * @date 2024-12-08
 */

#include "time_manager.h"
#include "logger.h"
#include <WiFi.h>
#include <cstdio>
#include <sys/time.h>
#include "esp_sntp.h"  // Direct ESP-IDF SNTP API for daemon control (esp_sntp_stop/init)

// ESP-IDF TAG convention for structured logging
static const char* TAG = "TIME";

// ============================================
// SINGLETON INSTANCE
// ============================================
TimeManager& timeManager = TimeManager::getInstance();

TimeManager& TimeManager::getInstance() {
    static TimeManager instance;
    return instance;
}

// ============================================
// CONSTRUCTOR
// ============================================
TimeManager::TimeManager()
    : initialized_(false)
    , synchronized_(false)
    , sntp_daemon_running_(false)
    , sync_completed_(false)
    , last_sync_time_(0)
    , last_sync_millis_(0)
    , last_resync_check_(0)
    , last_no_timestamp_log_ms_(0)
    , ntp_server_primary_(NTP_SERVER_PRIMARY)
    , ntp_server_secondary_(NTP_SERVER_SECONDARY)
    , ntp_server_tertiary_(NTP_SERVER_TERTIARY)
    , gateway_primary_buf_{} {
}

// ============================================
// SNTP CALLBACK (called by LWIP thread on successful sync)
// Must only set volatile flags — no heap allocation, no LOG calls.
// ============================================
static void onTimeSyncNotification(struct timeval* tv) {
    TimeManager::getInstance().onSyncCompleted();
}

// ============================================
// LIFECYCLE
// ============================================

bool TimeManager::begin() {
    if (initialized_) {
        // Reconnect path: daemon may be stopped after WiFi loss.
        // Ensure SNTP resumes when WiFi is back, even after initial begin().
        if (!sntp_daemon_running_ && WiFi.status() == WL_CONNECTED) {
            LOG_I(TAG, "TimeManager: Restarting SNTP daemon after reconnect");
            sync_completed_ = false;
            refreshPrimaryNtpFromGateway();
            configTime(NTP_GMT_OFFSET_SEC, NTP_DAYLIGHT_OFFSET,
                       ntp_server_primary_,
                       ntp_server_secondary_,
                       ntp_server_tertiary_);
            sntp_daemon_running_ = true;
            last_resync_check_ = millis();
        } else {
            LOG_W(TAG, "TimeManager already initialized");
        }
        return synchronized_;
    }

    LOG_I(TAG, "╔════════════════════════════════════════╗");
    LOG_I(TAG, "║  TimeManager: NTP Initialization       ║");
    LOG_I(TAG, "╚════════════════════════════════════════╝");

    // Check WiFi connection
    if (WiFi.status() != WL_CONNECTED) {
        LOG_E(TAG, "TimeManager: WiFi not connected - cannot sync NTP");
        LOG_E(TAG, "  Call TimeManager::begin() AFTER WiFi is connected");
        initialized_ = true;  // Mark as initialized but not synchronized
        return false;
    }

    refreshPrimaryNtpFromGateway();

    LOG_I(TAG, "TimeManager: Configuring NTP servers...");
    LOG_I(TAG, "  Primary:   " + String(ntp_server_primary_));
    LOG_I(TAG, "  Secondary: " + String(ntp_server_secondary_));
    LOG_I(TAG, "  Tertiary:  " + String(ntp_server_tertiary_));

    // CRITICAL: Set timezone to UTC BEFORE configTime
    // This ensures mktime() interprets tm structs as UTC, not local timezone.
    // Without this, mktime() uses the host system's timezone (e.g., CET on Windows/Wokwi),
    // causing a 1-hour offset between ESP32 timestamps and server time.
    setenv("TZ", "UTC0", 1);
    tzset();

    // Register callback BEFORE configTime so we don't miss a fast sync
    sync_completed_ = false;
    sntp_set_time_sync_notification_cb(onTimeSyncNotification);

    // Configure NTP (ESP32 IDF function)
    // Parameters: GMT offset (seconds), Daylight offset (seconds), NTP servers
    configTime(NTP_GMT_OFFSET_SEC, NTP_DAYLIGHT_OFFSET,
               ntp_server_primary_,
               ntp_server_secondary_,
               ntp_server_tertiary_);

    initialized_ = true;
    sntp_daemon_running_ = true;

    // Boot must not stall behind slow NTP replies:
    // wait only a short bounded window, then continue with background sync.
    unsigned long start = millis();
    while (!sync_completed_) {
        if (millis() - start > NTP_BOOT_WAIT_MS) {
            break;
        }
        delay(100);
    }

    // Mark check time so loop() retries after NTP_RESYNC_INTERVAL_MS, not immediately
    last_resync_check_ = millis();

    if (sync_completed_) {
        LOG_I(TAG, "╔════════════════════════════════════════╗");
        LOG_I(TAG, "║  NTP Sync Successful                   ║");
        LOG_I(TAG, "╚════════════════════════════════════════╝");
        LOG_I(TAG, "  Unix Timestamp: " + String((unsigned long)last_sync_time_));
        LOG_I(TAG, "  Formatted:      " + getFormattedTime());
        return true;
    } else {
        // Do NOT stop the daemon — it continues probing in background.
        LOG_W(TAG, "╔════════════════════════════════════════╗");
        LOG_W(TAG, "║  NTP Boot Wait elapsed                 ║");
        LOG_W(TAG, "╚════════════════════════════════════════╝");
        LOG_W(TAG, "  Continuing boot without blocking MQTT");
        LOG_W(TAG, "  SNTP daemon active — sync completes asynchronously");
        return false;
    }
}

void TimeManager::loop() {
    if (!initialized_) return;

    unsigned long now = millis();

    // Fall 1: Synchronisiert — periodisch validieren
    if (synchronized_) {
        if (now - last_resync_check_ >= NTP_RESYNC_INTERVAL_MS) {
            last_resync_check_ = now;
            if (!isValidTimestamp(time(nullptr))) {
                synchronized_ = false;
                LOG_W(TAG, "TimeManager: Time became invalid — marking as unsynced");
            }
        }
        return;
    }

    // Fall 2: Daemon laeuft — er probiert Server weiter, Callback setzt synchronized_
    if (sntp_daemon_running_) {
        return;
    }

    // Fall 3: Daemon gestoppt, noch nicht synced — periodisch neu starten
    if (now - last_resync_check_ >= NTP_RESYNC_INTERVAL_MS) {
        last_resync_check_ = now;
        if (WiFi.status() == WL_CONNECTED) {
            LOG_I(TAG, "TimeManager: Retrying NTP sync...");
            sync_completed_ = false;
            refreshPrimaryNtpFromGateway();
            configTime(NTP_GMT_OFFSET_SEC, NTP_DAYLIGHT_OFFSET,
                       ntp_server_primary_,
                       ntp_server_secondary_,
                       ntp_server_tertiary_);
            sntp_daemon_running_ = true;
        }
    }
}

// ============================================
// TIMESTAMP ACCESS
// ============================================

time_t TimeManager::getUnixTimestamp() const {
    if (!initialized_) {
        LOG_W(TAG, "TimeManager: Not initialized, returning 0");
        return 0;
    }
    
    // If synchronized, get fresh time from system
    if (synchronized_) {
        struct tm timeinfo;
        if (getSystemTime(&timeinfo)) {
            time_t current = mktime(&timeinfo);
            if (isValidTimestamp(current)) {
                return current;
            }
        }
    }
    
    // Fallback: estimate from last sync + elapsed millis
    if (last_sync_time_ > 0) {
        unsigned long elapsed_ms = millis() - last_sync_millis_;
        time_t estimated = last_sync_time_ + (elapsed_ms / 1000);
        
        if (isValidTimestamp(estimated)) {
            return estimated;
        }
    }
    
    // Last resort: return 0 to indicate no valid timestamp.
    // Rate-limit warning spam during early boot/config bursts while NTP is pending.
    unsigned long now_ms = millis();
    if (last_no_timestamp_log_ms_ == 0 ||
        (now_ms - last_no_timestamp_log_ms_) >= NTP_NO_TIMESTAMP_LOG_INTERVAL_MS) {
        last_no_timestamp_log_ms_ = now_ms;
        LOG_W(TAG, "TimeManager: No valid timestamp available");
    }
    return 0;
}

uint64_t TimeManager::getUnixTimestampMs() const {
    time_t seconds = getUnixTimestamp();
    
    if (seconds == 0) {
        return 0;
    }
    
    // Add millisecond precision from millis() delta
    unsigned long elapsed_since_sync = millis() - last_sync_millis_;
    unsigned long ms_fraction = elapsed_since_sync % 1000;
    
    return (uint64_t)seconds * 1000 + ms_fraction;
}

String TimeManager::getFormattedTime(const char* format) const {
    struct tm timeinfo;
    
    if (!getSystemTime(&timeinfo)) {
        return "TIME_NOT_AVAILABLE";
    }
    
    char buffer[64];
    strftime(buffer, sizeof(buffer), format, &timeinfo);
    return String(buffer);
}

// ============================================
// STATUS QUERIES
// ============================================

bool TimeManager::isSynchronized() const {
    return synchronized_ && isValidTimestamp(time(nullptr));
}

bool TimeManager::isSyncFresh() const {
    if (!synchronized_) {
        return false;
    }
    
    unsigned long elapsed = millis() - last_sync_millis_;
    return elapsed < NTP_RESYNC_INTERVAL_MS;
}

unsigned long TimeManager::getTimeSinceSync() const {
    if (!synchronized_) {
        return UINT32_MAX;
    }
    
    return millis() - last_sync_millis_;
}

String TimeManager::getSyncStatus() const {
    if (!initialized_) {
        return "NOT_INITIALIZED";
    }
    
    if (!synchronized_) {
        return "NOT_SYNCHRONIZED";
    }
    
    if (isSyncFresh()) {
        unsigned long age_sec = getTimeSinceSync() / 1000;
        return "SYNCHRONIZED (age: " + String(age_sec) + "s)";
    } else {
        return "SYNC_STALE (needs resync)";
    }
}

// ============================================
// MANUAL CONTROL
// ============================================

bool TimeManager::forceResync() {
    if (!initialized_) {
        LOG_E(TAG, "TimeManager: Cannot resync - not initialized");
        return false;
    }

    if (WiFi.status() != WL_CONNECTED) {
        LOG_E(TAG, "TimeManager: Cannot resync - WiFi disconnected");
        return false;
    }

    LOG_I(TAG, "TimeManager: Forcing NTP re-synchronization...");

    // Reset sync state before restarting daemon
    sync_completed_ = false;
    synchronized_ = false;

    // Stop daemon before reconfiguring — configTime/esp_sntp_init asserts if already running
    if (sntp_daemon_running_) {
        esp_sntp_stop();
        sntp_daemon_running_ = false;
    }

    refreshPrimaryNtpFromGateway();
    configTime(NTP_GMT_OFFSET_SEC, NTP_DAYLIGHT_OFFSET,
               ntp_server_primary_,
               ntp_server_secondary_,
               ntp_server_tertiary_);
    sntp_daemon_running_ = true;

    // Wait for callback-driven sync
    unsigned long start = millis();
    while (!sync_completed_) {
        if (millis() - start > NTP_SYNC_TIMEOUT_MS) {
            break;
        }
        delay(100);
    }

    if (!sync_completed_) {
        // Daemon bleibt laufen — er probiert weiter
        LOG_W(TAG, "TimeManager: forceResync timeout — daemon still active");
        return false;
    }
    return true;
}

void TimeManager::refreshPrimaryNtpFromGateway() {
    if (WiFi.status() != WL_CONNECTED) {
        return;
    }
    const IPAddress gw = WiFi.gatewayIP();
    if (gw == IPAddress(static_cast<uint32_t>(0))) {
        ntp_server_primary_ = NTP_SERVER_PRIMARY;
        return;
    }
    snprintf(gateway_primary_buf_, sizeof(gateway_primary_buf_), "%u.%u.%u.%u",
             static_cast<unsigned>(gw[0]), static_cast<unsigned>(gw[1]),
             static_cast<unsigned>(gw[2]), static_cast<unsigned>(gw[3]));
    ntp_server_primary_ = gateway_primary_buf_;
}

void TimeManager::setNTPServers(const char* primary, 
                                 const char* secondary,
                                 const char* tertiary) {
    ntp_server_primary_ = primary ? primary : NTP_SERVER_PRIMARY;
    ntp_server_secondary_ = secondary ? secondary : NTP_SERVER_SECONDARY;
    ntp_server_tertiary_ = tertiary ? tertiary : NTP_SERVER_TERTIARY;
    
    LOG_I(TAG, "TimeManager: NTP servers updated");
    LOG_I(TAG, "  Primary:   " + String(ntp_server_primary_));
    LOG_I(TAG, "  Secondary: " + String(ntp_server_secondary_));
    LOG_I(TAG, "  Tertiary:  " + String(ntp_server_tertiary_));
    
    // If already initialized, reconfigure
    if (initialized_) {
        configTime(NTP_GMT_OFFSET_SEC, NTP_DAYLIGHT_OFFSET,
                   ntp_server_primary_,
                   ntp_server_secondary_,
                   ntp_server_tertiary_);
    }
}

// ============================================
// WIFI EVENT CALLBACKS
// ============================================

void TimeManager::onSyncCompleted() {
    // Called from LWIP thread — only set volatile flags, no heap, no LOG
    synchronized_ = true;
    sync_completed_ = true;
    last_sync_time_ = time(nullptr);
    last_sync_millis_ = millis();
}

void TimeManager::onWiFiConnected() {
    if (!sntp_daemon_running_ && initialized_) {
        sync_completed_ = false;
        refreshPrimaryNtpFromGateway();
        configTime(NTP_GMT_OFFSET_SEC, NTP_DAYLIGHT_OFFSET,
                   ntp_server_primary_, ntp_server_secondary_, ntp_server_tertiary_);
        sntp_daemon_running_ = true;
        last_resync_check_ = millis();
        LOG_I(TAG, "SNTP daemon restarted after WiFi reconnect");
    }
}

void TimeManager::onWiFiDisconnected() {
    if (sntp_daemon_running_) {
        esp_sntp_stop();
        sntp_daemon_running_ = false;
        LOG_I(TAG, "SNTP daemon stopped — WiFi disconnected");
    }
}

bool TimeManager::syncFromAuthoritativeUnix(time_t unix_timestamp, const char* source) {
    if (!isValidTimestamp(unix_timestamp)) {
        LOG_W(TAG, "TimeManager: Ignoring invalid authoritative timestamp: " +
                   String((unsigned long)unix_timestamp));
        return false;
    }

    struct timeval tv;
    tv.tv_sec = unix_timestamp;
    tv.tv_usec = 0;

    if (settimeofday(&tv, nullptr) != 0) {
        LOG_E(TAG, "TimeManager: settimeofday failed for authoritative sync");
        return false;
    }

    synchronized_ = true;
    sync_completed_ = true;
    last_sync_time_ = unix_timestamp;
    last_sync_millis_ = millis();
    last_resync_check_ = last_sync_millis_;
    last_no_timestamp_log_ms_ = 0;

    LOG_I(TAG, "TimeManager: Clock seeded from " + String(source ? source : "external") +
               " (ts=" + String((unsigned long)unix_timestamp) + ")");
    return true;
}

// ============================================
// INTERNAL METHODS
// ============================================

bool TimeManager::synchronizeNTP(unsigned long timeout_ms) {
    struct tm timeinfo;
    unsigned long start = millis();
    uint8_t retries = 0;
    
    LOG_D(TAG, "TimeManager: Waiting for NTP sync (timeout: " + String(timeout_ms) + "ms)");
    
    while (retries < NTP_MAX_RETRIES) {
        // Check timeout
        if (millis() - start > timeout_ms) {
            LOG_W(TAG, "TimeManager: NTP sync timeout after " + String(timeout_ms) + "ms");
            return false;
        }
        
        // Try to get time
        if (getLocalTime(&timeinfo, NTP_RETRY_DELAY_MS)) {
            // Convert to Unix timestamp
            time_t now = mktime(&timeinfo);
            
            // Validate timestamp
            if (isValidTimestamp(now)) {
                // Success!
                synchronized_ = true;
                last_sync_time_ = now;
                last_sync_millis_ = millis();
                
                LOG_D(TAG, "TimeManager: NTP sync successful after " + 
                          String(retries + 1) + " attempt(s)");
                return true;
            } else {
                LOG_W(TAG, "TimeManager: Invalid timestamp received: " + String((unsigned long)now));
            }
        }
        
        retries++;
        LOG_D(TAG, "TimeManager: NTP retry " + String(retries) + "/" + String(NTP_MAX_RETRIES));
        
        // Small delay between retries
        delay(NTP_RETRY_DELAY_MS);
    }
    
    LOG_E(TAG, "TimeManager: NTP sync failed after " + String(NTP_MAX_RETRIES) + " retries");
    return false;
}

bool TimeManager::isValidTimestamp(time_t timestamp) const {
    // Sanity check: timestamp should be between 2023 and 2049
    return (timestamp >= NTP_MIN_VALID_TIMESTAMP && 
            timestamp <= NTP_MAX_VALID_TIMESTAMP);
}

bool TimeManager::getSystemTime(struct tm* out_time) const {
    if (!out_time) {
        return false;
    }
    
    // getLocalTime is ESP32-specific, returns false if time not set
    return getLocalTime(out_time, 0);  // Non-blocking
}

