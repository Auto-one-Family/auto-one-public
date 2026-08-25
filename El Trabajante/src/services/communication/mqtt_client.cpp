#include "mqtt_client.h"
#include "../../utils/mqtt_broker_sanitize.h"
#include "../../models/error_codes.h"
#include "../../services/config/config_manager.h"
#include "../../services/sensor/sensor_manager.h"
#include "../../services/actuator/actuator_manager.h"
#include "../../services/safety/offline_mode_manager.h"
#include "../../services/communication/wifi_manager.h"
#include "../../utils/time_manager.h"
#include "../../config/feature_flags.h"
#include "../../config/firmware_version.h"

#ifdef XIAO_ESP32C3
    #include "../../config/hardware/xiao_esp32c3.h"
#elif defined(ESP32_S3_DEVKIT_MODE)
    #include "../../config/hardware/esp32_s3_devkit.h"
#else
    #include "../../config/hardware/esp32_dev.h"
#endif

#include <WiFi.h>
#include <sdkconfig.h>
#include <esp_system.h>
#include <esp_heap_caps.h>
#include <atomic>
#include <cstring>
#include <errno.h>

#include "../../tasks/intent_contract.h"
#include "../../tasks/sensor_command_queue.h"   // For queue overflow telemetry (AUT-5)
// AUT-714: Spool flush on reconnect
#include "../../services/spool/spool_manager.h"

#ifndef MQTT_USE_PUBSUBCLIENT
    #include "../../tasks/safety_task.h"         // g_safety_task_handle, NOTIFY_* bits
    #include "../../tasks/publish_queue.h"       // M3: Core 1 → Core 0 publish queue
    #include "../../tasks/publish_queue_policy.h"
    #include "../../error_handling/error_tracker.h"
    // Forward declarations from main.cpp
    extern void routeIncomingMessage(const char* topic, const char* payload);
#endif

// ESP-IDF TAG convention for structured logging
static const char* TAG = "MQTT";

// Shared by safePublish (both backends) and processPublishQueue (ESP-IDF only).
static bool isCriticalPublishTopic(const String& topic) {
    // AUT-344 / AUT-331: lifecycle is QoS-0 observability; substring "/system/intent_outcome"
    // would incorrectly mark it critical and disable publish-queue shed for chain-stage bursts.
    if (topic.indexOf("/system/intent_outcome/lifecycle") >= 0) {
        return false;
    }
    return topic.indexOf("/alert") != -1 ||
           topic.indexOf("/response") != -1 ||
           topic.indexOf("/config_response") != -1 ||
           topic.indexOf("/zone/ack") != -1 ||
           topic.indexOf("/subzone/ack") != -1 ||
           topic.indexOf("/system/error") != -1 ||
           topic.indexOf("/system/intent_outcome") != -1;
}

static bool isRealtimeResponsePublishTopic(const String& topic) {
    return (topic.indexOf("/actuator/") != -1 && topic.indexOf("/response") != -1) ||
           (topic.indexOf("/sensor/") != -1 && topic.indexOf("/response") != -1) ||
           topic.indexOf("/config_response") != -1 ||
           topic.indexOf("/zone/ack") != -1 ||
           topic.indexOf("/subzone/ack") != -1 ||
           topic.indexOf("/system/command/response") != -1;
}

static bool isIntentOutcomePublishTopic(const String& topic) {
    return topic.indexOf("/system/intent_outcome") != -1;
}

static const char* publishFailureReasonClassToString(PublishFailureReasonClass reason) {
    switch (reason) {
        case PublishFailureReasonClass::CircuitBreakerOpen:
            return "cb_open";
        case PublishFailureReasonClass::QueueShed:
            return "queue_shed";
        case PublishFailureReasonClass::OutboxFull:
            return "outbox_full";
        case PublishFailureReasonClass::TransportError:
            return "transport_error";
        case PublishFailureReasonClass::None:
        default:
            return "transport_error";
    }
}

#ifndef MQTT_USE_PUBSUBCLIENT
static PublishFailureReasonClass mapQueueEnqueueResultToFailureReason(PublishQueueEnqueueResult result) {
    const char* reason = publishQueueEnqueueReasonClass(result);
    if (reason != nullptr && strcmp(reason, "queue_shed") == 0) {
        return PublishFailureReasonClass::QueueShed;
    }
    return PublishFailureReasonClass::TransportError;
}
#endif

#ifndef MQTT_USE_PUBSUBCLIENT
static std::atomic<uint32_t> g_publish_outbox_noncritical_drops{0};
// [FIX5-VERIFY] Total MQTT outbox-full events (msg_id == -2), all topic classes.
// Distinct from noncritical_drops: critical topics hit NVS replay instead of drop,
// but still count as outbox-full events — this counter tracks event frequency.
static std::atomic<uint32_t> g_publish_outbox_full_count{0};
// Counts QoS-1 PUBACK events (MQTT_EVENT_PUBLISHED). Pairing [OUTBOX+1] enqueue
// count against [OUTBOX-1] PUBACK count reveals OUTBOX accumulation rate.
static std::atomic<uint32_t> g_puback_count{0};
static std::atomic<uint32_t> g_qos1_enqueue_count{0};
static std::atomic<uint32_t> g_safe_publish_backpressure_abort_count{0};
// True while routeIncomingMessage() executes inside MQTT_EVENT_DATA callback.
// Publishing directly from this context can re-enter MQTT internals on Core 0.
static std::atomic<bool> g_in_mqtt_event_callback{false};

static constexpr unsigned long MANAGED_RECONNECT_BASE_DELAY_MS = 1500;
static constexpr unsigned long MANAGED_RECONNECT_MAX_DELAY_MS = 12000;
// Hold reconnect requests briefly after disconnect so transport/WiFi can settle.
static constexpr unsigned long MANAGED_RECONNECT_AUTO_GRACE_MS = 15000;
// AUT-676: is_connecting_ Zeit-Watchdog — if no MQTT event clears the flag within this
// window after reconnect()→ESP_OK, force-clear and retry (guards TCP-SYN stuck / silent IDF).
static constexpr unsigned long MANAGED_RECONNECT_CONNECTING_WATCHDOG_MS = 30000;

// PKG-18 (INC-2026-04-11-ea5484): Standby-resume disconnect loop hardening.
// After this many write timeouts without intervening connect-success,
// boost reconnect delay and extend post-reconnect queue stabilization.
// Runtime evidence (H45/H46): a single write-timeout can already trigger
// reconnect churn; threshold=3 delayed mitigation too long.
static constexpr uint32_t WRITE_TIMEOUT_ESCALATION_THRESHOLD = 1;
// Boosted reconnect base delay after write-timeout episodes (vs 1500ms default).
static constexpr unsigned long MANAGED_RECONNECT_WRITE_TIMEOUT_BOOST_MS = 5000;
// Post-reconnect queue hold after write-timeout history — lets TCP/TLS
// handshake and first keepalive round-trip complete before queue drain.
static constexpr uint32_t POST_RECONNECT_TRANSPORT_SETTLE_MS = 2000;

// ESP-IDF default network_timeout_ms = 10000 keeps transport write stalls bounded.
// For this project we intentionally keep this lower (1500ms), because actuator control
// depends on short control-loop latency. A very high timeout can make a single publish
// block long enough to delay subsequent actuator responses in the UI path.
// Trade-off:
// - lower timeout => faster recovery from degraded transport, less control lag
// - higher timeout => fewer transient write timeouts, but higher risk of long stalls
// Runtime tuning is driven by stress logs (queue/drain/direct publish durations).
static constexpr int MQTT_CLIENT_NETWORK_TIMEOUT_MS = 1500;

// [AUT-656-D/AUT-1075] task_stack must track the post-init max_alloc floor — a fixed
// 12288 collided with max_alloc=12276 (12 B short). Runtime value: g_mqtt_runtime_task_stack.
static constexpr int MQTT_CLIENT_TASK_STACK_MIN      = 10240;  // AUT-569 measured stack usage
static constexpr int MQTT_CLIENT_TASK_STACK_CEILING  = 12288;
static constexpr int MQTT_CLIENT_TASK_STACK_TCB_BYTES    = 512;
static constexpr int MQTT_CLIENT_TASK_STACK_SAFETY_BYTES = 1024;

static int g_mqtt_runtime_task_stack = MQTT_CLIENT_TASK_STACK_CEILING;

static int computeMqttTaskStackFromMaxAlloc(size_t max_alloc) {
    const int budget = static_cast<int>(max_alloc)
                     - MQTT_CLIENT_TASK_STACK_TCB_BYTES
                     - MQTT_CLIENT_TASK_STACK_SAFETY_BYTES;
    if (budget < MQTT_CLIENT_TASK_STACK_MIN) {
        return MQTT_CLIENT_TASK_STACK_MIN;
    }
    if (budget > MQTT_CLIENT_TASK_STACK_CEILING) {
        return MQTT_CLIENT_TASK_STACK_CEILING;
    }
    return budget;
}

static bool mqttTaskStackPreflightOk(int task_stack) {
    const size_t max_alloc = heap_caps_get_largest_free_block(MALLOC_CAP_DEFAULT);
    return max_alloc >= static_cast<size_t>(task_stack + MQTT_CLIENT_TASK_STACK_TCB_BYTES);
}

static bool shouldLogAdmissionCorrelation(const String& topic) {
    return topic.indexOf("/command") != -1 ||
           topic.indexOf("/config") != -1 ||
           topic.indexOf("/zone/") != -1 ||
           topic.indexOf("/subzone/") != -1;
}

static void logAdmissionCorrelationBlockedPublish(const String& topic,
                                                  const String& payload,
                                                  const char* reason_code) {
    if (!shouldLogAdmissionCorrelation(topic)) {
        return;
    }
    IntentMetadata metadata = extractIntentMetadataFromPayload(payload.c_str(), "admission");
    // [FIX3-VERIFY] snprintf on stack — previous String-concat was OOM-risky on the
    // OUTBOX-pressure path where this function is called (safePublish blocked).
    char log_buf[256];
    snprintf(log_buf, sizeof(log_buf),
             "[ADMISSION][FIX3-VERIFY] blocked reason=%s topic=%s intent=%s corr=%s epoch=%lu",
             reason_code != nullptr ? reason_code : "UNKNOWN",
             topic.c_str(),
             metadata.intent_id,
             metadata.correlation_id,
             (unsigned long)metadata.epoch_at_accept);
    log_buf[sizeof(log_buf) - 1] = '\0';
    LOG_W(TAG, log_buf);
}

static bool isWritePathTimeoutErrno(int sock_errno) {
    return sock_errno == ETIMEDOUT || sock_errno == EAGAIN || sock_errno == EWOULDBLOCK ||
           sock_errno == 119;  // historical ESP32 marker from field logs
}

static bool isWritePathTimeoutSignal(int sock_errno, int tls_stack_err) {
    if (isWritePathTimeoutErrno(sock_errno)) {
        return true;
    }

    // Some IDF paths propagate timeout errno only via tls_stack_err.
    const int normalized_stack_errno = (tls_stack_err < 0) ? -tls_stack_err : tls_stack_err;
    return isWritePathTimeoutErrno(normalized_stack_errno);
}

static bool isTlsConnectTimeout(esp_err_t tls_err) {
    const char* tls_name = esp_err_to_name(tls_err);
    return tls_name != nullptr && strstr(tls_name, "CONNECTION_TIMEOUT") != nullptr;
}

// AUT-67 (EA-14): ESP-IDF v4.x does NOT propagate errno from esp_transport_write()
// into event->error_handle when the write path times out ("Writing didn't complete
// in specified timeout: errno=119"). The event arrives as
//   error_type = MQTT_ERROR_TYPE_TCP_TRANSPORT
//   esp_transport_sock_errno = 0
//   esp_tls_stack_err        = 0
//   esp_tls_last_esp_err     = ESP_OK
// i.e. **all transport fields neutral** while the kernel-level ESP_LOG has already
// printed the timeout. Genuine TCP errors always carry a non-zero sock_errno;
// genuine TLS errors always carry a non-ESP_OK tls_last_err. Therefore an
// all-neutral TCP_TRANSPORT event is with very high probability the IDF-internal
// write-path timeout. We classify it as such so that the write_timeouts counter
// reflects reality and the last_transport_errno marker stays meaningful for
// SafePublish/Backpressure heuristics that consume it.
static bool isSilentWritePathError(int sock_errno, int tls_stack_err, esp_err_t tls_last_err) {
    return sock_errno == 0 && tls_stack_err == 0 && tls_last_err == ESP_OK;
}
#else
static void logAdmissionCorrelationBlockedPublish(const String& topic,
                                                  const String& payload,
                                                  const char* reason_code) {
    (void)topic;
    (void)payload;
    (void)reason_code;
}
#endif

// ============================================
// EXTERNAL GLOBAL VARIABLES (from main.cpp)
// ============================================
extern KaiserZone g_kaiser;
extern SystemConfig g_system_config;
extern uint32_t getEmergencyRejectedNoTokenCount();

#ifndef MQTT_USE_PUBSUBCLIENT
// Apply fields that esp_mqtt_set_config() would zero-reset if omitted (AUT-656-B).
// Must include LWT — a partial struct clobbers will registration (AUT-1075-LWT).
static void applyMqttRuntimeConfig(esp_mqtt_client_handle_t client, int task_stack) {
    if (client == nullptr) {
        return;
    }
    time_t will_ts = timeManager.getUnixTimestamp();
    char lw_msg[160];
    snprintf(lw_msg, sizeof(lw_msg),
             "{\"status\":\"offline\",\"esp_id\":\"%s\","
             "\"reason\":\"unexpected_disconnect\",\"timestamp\":%lu}",
             g_system_config.esp_id.c_str(), (unsigned long)will_ts);
    String lw_topic = String(TopicBuilder::buildSystemHeartbeatTopic());
    lw_topic.replace("/heartbeat", "/will");

    esp_mqtt_client_config_t cfg = {};
    cfg.disable_auto_reconnect = true;
    cfg.network_timeout_ms     = MQTT_CLIENT_NETWORK_TIMEOUT_MS;
    cfg.task_stack             = task_stack;
    cfg.task_prio              = 3;
    cfg.lwt_topic              = lw_topic.c_str();
    cfg.lwt_msg                = lw_msg;
    cfg.lwt_qos                = 1;
    cfg.lwt_retain             = 1;
    esp_mqtt_set_config(client, &cfg);
}

#endif

static String g_boot_sequence_id;
static uint8_t g_boot_reset_reason = 0;
static unsigned long g_segment_start_ts = 0;

static const char* resetReasonToString(uint8_t reason) {
    switch (reason) {
        case ESP_RST_POWERON: return "POWERON";
        case ESP_RST_EXT: return "EXT";
        case ESP_RST_SW: return "SW";
        case ESP_RST_PANIC: return "PANIC";
        case ESP_RST_INT_WDT: return "INT_WDT";
        case ESP_RST_TASK_WDT: return "TASK_WDT";
        case ESP_RST_WDT: return "WDT";
        case ESP_RST_DEEPSLEEP: return "DEEPSLEEP";
        case ESP_RST_BROWNOUT: return "BROWNOUT";
        case ESP_RST_SDIO: return "SDIO";
        default: return "UNKNOWN";
    }
}

static void ensureBootTelemetryInitialized(time_t unix_timestamp, bool time_valid) {
    if (g_boot_sequence_id.length() == 0) {
        g_boot_reset_reason = static_cast<uint8_t>(esp_reset_reason());
        g_boot_sequence_id = g_system_config.esp_id + "-b" + String(g_system_config.boot_count) +
                             "-r" + String(g_boot_reset_reason);
    }
    if (g_segment_start_ts == 0 && time_valid && unix_timestamp > 0) {
        g_segment_start_ts = static_cast<unsigned long>(unix_timestamp);
    }
}

// ============================================
// SHARED ATOMIC STATE (SAFETY-RTOS M2)
// Written by MQTT_EVENT_CONNECTED/DISCONNECTED (Core 0 — MQTT event task).
// Read by checkServerAckTimeout() in Safety-Task (Core 1) via mqttClient.isConnected().
// ============================================
#ifndef MQTT_USE_PUBSUBCLIENT
std::atomic<bool> g_mqtt_connected{false};
#endif

// ============================================
// CONSTANTS (PubSubClient path — seeed/wokwi only)
// ============================================
#ifdef MQTT_USE_PUBSUBCLIENT
const unsigned long RECONNECT_BASE_DELAY_MS = 1000;   // 1 second
const unsigned long RECONNECT_MAX_DELAY_MS = 60000;   // 60 seconds
const uint16_t MAX_RECONNECT_ATTEMPTS = 10;
#endif

// ============================================
// STATIC MEMBERS
// ============================================
MQTTClient* MQTTClient::instance_ = nullptr;
std::function<void(const String&, const String&)> MQTTClient::test_publish_hook_;

// ============================================
// GLOBAL MQTT CLIENT INSTANCE
// ============================================
MQTTClient& mqttClient = MQTTClient::getInstance();

// ============================================
// SINGLETON IMPLEMENTATION
// ============================================
MQTTClient& MQTTClient::getInstance() {
    static MQTTClient instance;
    instance_ = &instance;
    return instance;
}

// ============================================
// CONSTRUCTOR / DESTRUCTOR
// ============================================
MQTTClient::MQTTClient()
    :
#ifndef MQTT_USE_PUBSUBCLIENT
      mqtt_client_(nullptr),
#else
      mqtt_(wifi_client_),
      offline_buffer_count_(0),
      last_reconnect_attempt_(0),
      reconnect_attempts_(0),
      reconnect_delay_ms_(RECONNECT_BASE_DELAY_MS),
#endif
      initialized_(false),
      anonymous_mode_(true),
      last_heartbeat_(0),
      circuit_breaker_("MQTT", 5, 30000, 10000),
      registration_confirmed_(false),
      registration_start_ms_(0),
      registration_timeout_logged_(false),
#ifndef MQTT_USE_PUBSUBCLIENT
      pending_subscription_count_(0),
      bootstrap_heartbeat_pending_(false),
      pending_bootstrap_ack_subscribe_msg_id_(-1),
      pending_bootstrap_config_subscribe_msg_id_(-1),
      bootstrap_ack_subscription_ready_(false),
      bootstrap_config_subscription_ready_(false),
      bootstrap_heartbeat_send_pending_(false),
      next_managed_reconnect_ms_(0),
      managed_reconnect_attempts_(0),
      is_connecting_(false),
      is_connecting_since_ms_(0),
      transport_write_timeout_count_(0),
      tls_connect_timeout_count_(0),
      tcp_transport_error_count_(0),
      last_transport_errno_(0),
      last_disconnect_ms_(0),
      manual_reconnect_suspended_(false),
      pending_session_announce_msg_id_(-1),
      last_runtime_critical_publish_ms_(0UL),
      last_disconnect_reason_{0},
      last_disconnect_rssi_(0),
      last_disconnect_wifi_connected_(false),
      last_disconnect_pending_report_(false),
#endif
      publish_seq_(0),
      safe_publish_retry_count_(0),
      last_publish_failure_reason_(PublishFailureReasonClass::None)
#ifdef ENABLE_METRICS_SPLIT
      , last_metrics_{}
      , metrics_skip_count_(METRICS_MAX_SKIP_COUNT)
#endif
      {
    // Circuit Breaker configured:
    // - 5 failures → OPEN
    // - 30s recovery timeout
    // - 10s half-open test timeout
}

MQTTClient::~MQTTClient() {
    disconnect();
}

// ============================================
// INITIALIZATION
// ============================================
bool MQTTClient::begin() {
    if (initialized_) {
        LOG_W(TAG, "MQTTClient already initialized");
        return true;
    }

#ifdef MQTT_USE_PUBSUBCLIENT
    mqtt_.setCallback(staticCallback);
#endif

    initialized_ = true;
    LOG_I(TAG, "MQTTClient initialized");
    return true;
}

// ============================================
// CONNECTION MANAGEMENT
// ============================================
bool MQTTClient::connect(const MQTTConfig& config) {
    if (!initialized_) {
        LOG_E(TAG, "MQTTClient not initialized");
        errorTracker.logCommunicationError(ERROR_MQTT_INIT_FAILED, "MQTTClient not initialized");
        return false;
    }

    String broker_host = config.server;
    uint16_t broker_port = config.port;
    sanitizeMqttBrokerHostAndPort(broker_host, &broker_port);

    if (broker_host.length() == 0) {
        LOG_E(TAG, "MQTT server address is empty");
        errorTracker.logCommunicationError(ERROR_MQTT_INIT_FAILED, "MQTT server address is empty");
        return false;
    }

    if (broker_host != config.server || broker_port != config.port) {
        LOG_W(TAG, "MQTT broker host aus Config normalisiert (Transport): \"" + config.server + "\":" +
                   String(config.port) + " -> \"" + broker_host + "\":" + String(broker_port));
    }

    current_config_ = config;
    current_config_.server = broker_host;
    current_config_.port = broker_port;
    anonymous_mode_ = (config.username.length() == 0);

    if (anonymous_mode_) {
        LOG_I(TAG, "MQTT connecting in Anonymous Mode");
    } else {
        LOG_I(TAG, "MQTT connecting with authentication");
    }

#ifndef MQTT_USE_PUBSUBCLIENT
    // ============================================
    // SAFETY-RTOS M2: ESP-IDF MQTT — NON-BLOCKING
    // esp_mqtt_client_start() returns immediately.
    // MQTT_EVENT_CONNECTED fires asynchronously when connection is established.
    // ============================================

    // Build broker URI: "mqtt://hostname:port" (plain TCP; kein mqtts ohne TLS-Stack)
    char broker_uri[96];
    snprintf(broker_uri, sizeof(broker_uri), "mqtt://%s:%d",
             broker_host.c_str(), broker_port);

    // Build Last-Will topic: kaiser/{k}/esp/{e}/system/will
    // Use heartbeat topic as base and replace /heartbeat with /will
    String lw_topic_str = String(TopicBuilder::buildSystemHeartbeatTopic());
    lw_topic_str.replace("/heartbeat", "/will");

    // Build Last-Will payload (JSON)
    time_t will_ts = timeManager.getUnixTimestamp();
    char lw_msg[160];
    snprintf(lw_msg, sizeof(lw_msg),
             "{\"status\":\"offline\",\"esp_id\":\"%s\",\"reason\":\"unexpected_disconnect\",\"timestamp\":%lu}",
             g_system_config.esp_id.c_str(), (unsigned long)will_ts);

    LOG_I(TAG, "Broker URI: " + String(broker_uri));
    LOG_I(TAG, "Last-Will Topic: " + lw_topic_str);

    // ESP-IDF v4.x flache esp_mqtt_client_config_t (Arduino-ESP32 3.x) — nicht die v5-Nested-Struct.
    esp_mqtt_client_config_t mqtt_cfg = {};
    mqtt_cfg.uri = broker_uri;
    mqtt_cfg.keepalive = config.keepalive;
    mqtt_cfg.disable_clean_session = 0;
    // Keep reconnect orchestration in one place (processManagedReconnect_).
    // Runtime logs showed IDF auto-reconnect causing repeated TLS-timeout
    // disconnect churn before the managed backoff/jitter path could stabilize.
    mqtt_cfg.disable_auto_reconnect = true;

    mqtt_cfg.lwt_topic = lw_topic_str.c_str();
    mqtt_cfg.lwt_msg = lw_msg;
    mqtt_cfg.lwt_qos = 1;
    mqtt_cfg.lwt_retain = 1;
    mqtt_cfg.lwt_msg_len = 0;

    // Inbound buffer: config topic full-state JSON can exceed 4 KB (CP-F4 / CONFIG_PAYLOAD_MAX_LEN).
    // Oversized frames still reassemble into data_buf (8192) below; keep buffer aligned with field sizes.
    mqtt_cfg.buffer_size = 8192;
    // Extra outbox headroom reduces transport write pressure during command bursts
    // (e.g. calibration/manual measurement + heartbeat + responses).
    mqtt_cfg.out_buffer_size = 8192;
    // AUT-477: Flat esp_mqtt_client_config_t (Arduino-ESP32 SDK) has no runtime outbox.limit;
    // OUTBOX capacity is compile-time in prebuilt libmqtt.a (default 4096 B).
    // sdkconfig.defaults CONFIG_MQTT_OUTBOX_SIZE_BYTES=16384 does NOT apply to Arduino
    // framework builds — runtime size is logged after MQTT_EVENT_CONNECTED.
#if defined(CONFIG_MQTT_OUTBOX_SIZE_BYTES) && (CONFIG_MQTT_OUTBOX_SIZE_BYTES < 16384)
#warning "AUT-477: CONFIG_MQTT_OUTBOX_SIZE_BYTES below 16384 — transport burst risk"
#endif
#if !defined(CONFIG_MQTT_OUTBOX_SIZE_BYTES)
#pragma message("AUT-477: CONFIG_MQTT_OUTBOX_SIZE_BYTES undefined — expect prebuilt libmqtt OUTBOX=4096")
#endif

    mqtt_cfg.client_id = config.client_id.c_str();
    if (!anonymous_mode_) {
        mqtt_cfg.username = config.username.c_str();
        mqtt_cfg.password = config.password.c_str();
    }

    // [AUT-569/AUT-1075] task_stack: derived from max_alloc floor, not a fixed constant.
    g_mqtt_runtime_task_stack = computeMqttTaskStackFromMaxAlloc(
        heap_caps_get_largest_free_block(MALLOC_CAP_DEFAULT));
    mqtt_cfg.task_stack = g_mqtt_runtime_task_stack;
    mqtt_cfg.task_prio = 3;

    // AUT-54: Override IDF default network_timeout_ms (10s). Field logs showed write-path
    // disconnects ~10s after bursts — that default caps blocking transport writes.
    mqtt_cfg.network_timeout_ms = MQTT_CLIENT_NETWORK_TIMEOUT_MS;

    // Destroy old client if present (e.g. reconnect after config change)
    if (mqtt_client_ != nullptr) {
        esp_mqtt_client_stop(mqtt_client_);
        esp_mqtt_client_destroy(mqtt_client_);
        mqtt_client_ = nullptr;
    }

    mqtt_client_ = esp_mqtt_client_init(&mqtt_cfg);
    g_mqtt_runtime_task_stack = computeMqttTaskStackFromMaxAlloc(
        heap_caps_get_largest_free_block(MALLOC_CAP_DEFAULT));
    applyMqttRuntimeConfig(mqtt_client_, g_mqtt_runtime_task_stack);
    LOG_W(TAG, String("[AUT-656-D5] max_alloc_after_init=") +
               String((int)heap_caps_get_largest_free_block(MALLOC_CAP_DEFAULT)) +
               " task_stack=" + String(g_mqtt_runtime_task_stack));
    if (mqtt_client_ == nullptr) {
        LOG_E(TAG, "esp_mqtt_client_init() failed — nullptr returned");
        errorTracker.logCommunicationError(ERROR_MQTT_INIT_FAILED, "esp_mqtt_client_init failed");
        return false;
    }

    // Reset Registration Gate
    registration_confirmed_ = false;
    registration_start_ms_  = millis();
    registration_timeout_logged_ = false;
    next_managed_reconnect_ms_ = 0;
    managed_reconnect_attempts_ = 0;
    is_connecting_ = false;
    is_connecting_since_ms_ = 0;
    transport_write_timeout_count_ = 0;
    tls_connect_timeout_count_ = 0;
    tcp_transport_error_count_ = 0;
    last_transport_errno_ = 0;
    last_disconnect_ms_ = 0;

    // Register event handler (args = this, so handler can access members)
    esp_mqtt_client_register_event(mqtt_client_, MQTT_EVENT_ANY, mqtt_event_handler, this);

    // Start client — NON-BLOCKING. Connection happens in background MQTT task.
    esp_err_t err = ESP_FAIL;
    // [AUT-569/AUT-1075] Preflight max_alloc before start; retry after lwIP PCB GC.
    for (int retry = 0; retry < 3; ++retry) {
        g_mqtt_runtime_task_stack = computeMqttTaskStackFromMaxAlloc(
            heap_caps_get_largest_free_block(MALLOC_CAP_DEFAULT));
        applyMqttRuntimeConfig(mqtt_client_, g_mqtt_runtime_task_stack);
        if (!mqttTaskStackPreflightOk(g_mqtt_runtime_task_stack)) {
            LOG_W(TAG, String("[AUT-1075] start preflight blocked retry ") + String(retry + 1) +
                       " max_alloc=" + String((int)heap_caps_get_largest_free_block(MALLOC_CAP_DEFAULT)) +
                       " task_stack=" + String(g_mqtt_runtime_task_stack));
            vTaskDelay(pdMS_TO_TICKS(500));
            continue;
        }
        err = esp_mqtt_client_start(mqtt_client_);
        if (err == ESP_OK) {
            break;
        }
        LOG_W(TAG, String("[AUT-569] esp_mqtt_client_start retry ") + String(retry + 1) +
                       " heap=" + String((int)heap_caps_get_free_size(MALLOC_CAP_DEFAULT)) +
                       " max_alloc=" + String((int)heap_caps_get_largest_free_block(MALLOC_CAP_DEFAULT)) +
                       " task_stack=" + String(g_mqtt_runtime_task_stack));
        vTaskDelay(pdMS_TO_TICKS(500));
    }
    if (err != ESP_OK) {
        LOG_E(TAG, String("esp_mqtt_client_start() failed: ") + esp_err_to_name(err));
        errorTracker.logCommunicationError(ERROR_MQTT_CONNECT_FAILED,
                                           "esp_mqtt_client_start failed");
        esp_mqtt_client_destroy(mqtt_client_);
        mqtt_client_ = nullptr;
        return false;
    }

    // NOTE (M2): connect() returns true immediately — actual MQTT connection is async.
    // MQTT_EVENT_CONNECTED fires when broker accepts the connection.
    // Consequence: mqttClient.connect() in setup() will NOT fail even if broker is unreachable.
    // Portal recovery for MQTT failure now happens via the 5-minute persistent-failure timer
    // in loop() (CircuitBreaker OPEN → provisionManager.startAPModeForReconfig()).
    LOG_I(TAG, "[M2] ESP-IDF MQTT client started — connecting in background");
    // [FIX2-VERIFY] Log MQTT buffer config at connect time so serial monitor confirms
    // CONFIG_MQTT_OUTBOX_SIZE_BYTES from sdkconfig is active.
    // out_buffer_size is the transport send buffer (runtime); OUTBOX is compile-time sdkconfig.
    // compile-time CONFIG_MQTT_* may be absent with Arduino prebuilt SDK; runtime OUTBOX
    // is additionally logged in MQTT_EVENT_CONNECTED via esp_mqtt_client_get_outbox_size().
    {
        char cfg_log[192];
#if defined(CONFIG_MQTT_OUTBOX_EXPIRED_TIMEOUT_MS)
        const unsigned outbox_expiry_ms = static_cast<unsigned>(CONFIG_MQTT_OUTBOX_EXPIRED_TIMEOUT_MS);
#else
        const unsigned outbox_expiry_ms = 0U;
#endif
#if defined(CONFIG_MQTT_OUTBOX_SIZE_BYTES)
        const unsigned outbox_compile_bytes = static_cast<unsigned>(CONFIG_MQTT_OUTBOX_SIZE_BYTES);
#else
        const unsigned outbox_compile_bytes = 0U;
#endif
        snprintf(cfg_log, sizeof(cfg_log),
                 "[FIX2-VERIFY] MQTT cfg: out_buffer=%u buffer=%u "
                 "OUTBOX_COMPILE=%u runtime_logged_on_connect expiry=%ums net_timeout=%dms",
                 (unsigned)mqtt_cfg.out_buffer_size,
                 (unsigned)mqtt_cfg.buffer_size,
                 outbox_compile_bytes,
                 outbox_expiry_ms,
                 mqtt_cfg.network_timeout_ms);
        LOG_I(TAG, cfg_log);
    }
    return true;

#else
    // ============================================
    // PubSubClient path (seeed, wokwi — MQTT_USE_PUBSUBCLIENT=1)
    // ============================================
    reconnect_attempts_ = 0;
    reconnect_delay_ms_ = RECONNECT_BASE_DELAY_MS;

    mqtt_.setServer(config.server.c_str(), config.port);
    mqtt_.setKeepAlive(config.keepalive);

    return connectToBroker();
#endif
}

bool MQTTClient::disconnect() {
#ifndef MQTT_USE_PUBSUBCLIENT
    if (mqtt_client_ != nullptr) {
        const esp_err_t err = esp_mqtt_client_disconnect(mqtt_client_);
        if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
            LOG_W(TAG, String("esp_mqtt_client_disconnect() returned ") + esp_err_to_name(err));
        }
        g_mqtt_connected.store(false);
        // Ensure managed reconnect can recover after explicit local disconnect requests.
        last_disconnect_ms_ = millis();
        if (next_managed_reconnect_ms_ == 0) {
            scheduleManagedReconnect_("local_disconnect", MANAGED_RECONNECT_BASE_DELAY_MS);
        }
        LOG_I(TAG, "MQTT disconnected (ESP-IDF transport detached, client kept alive)");
    }
    return true;
#else
    if (mqtt_.connected()) {
        mqtt_.disconnect();
        LOG_I(TAG, "MQTT disconnected");
    }
    return true;
#endif
}

bool MQTTClient::isConnected() {
#ifndef MQTT_USE_PUBSUBCLIENT
    return g_mqtt_connected.load();
#else
    return mqtt_.connected();
#endif
}

void MQTTClient::reconnect() {
#ifndef MQTT_USE_PUBSUBCLIENT
    // ESP-IDF reconnects automatically — no manual reconnect needed.
    // This method is kept for interface compatibility (called from loop() in PubSubClient path).
    // In ESP-IDF path loop() does not call reconnect().
#else
    if (isConnected()) {
        LOG_D(TAG, "MQTT already connected");
        circuit_breaker_.recordSuccess();
        return;
    }

    if (!circuit_breaker_.allowRequest()) {
        static unsigned long last_circuit_breaker_log = 0;
        unsigned long now = millis();
        if (now - last_circuit_breaker_log > 1000) {
            last_circuit_breaker_log = now;
            LOG_D(TAG, "MQTT reconnect blocked by Circuit Breaker (waiting for recovery)");
        }
        return;
    }

    if (!shouldAttemptReconnect()) {
        return;
    }

    reconnect_attempts_++;
    last_reconnect_attempt_ = millis();

    LOG_I(TAG, "Attempting MQTT reconnection (attempt " + String(reconnect_attempts_) + ")");

    if (!connectToBroker()) {
        circuit_breaker_.recordFailure();
        reconnect_delay_ms_ = calculateBackoffDelay();
        if (circuit_breaker_.isOpen()) {
            LOG_W(TAG, "Circuit Breaker OPENED after reconnect failures");
        }
    } else {
        circuit_breaker_.recordSuccess();
    }
#endif
}

// ============================================
// AUTHENTICATION TRANSITION
// ============================================
bool MQTTClient::transitionToAuthenticated(const String& username, const String& password) {
    if (!anonymous_mode_) {
        LOG_W(TAG, "Already in authenticated mode");
        return true;
    }

    LOG_I(TAG, "Transitioning from Anonymous to Authenticated mode");

    current_config_.username = username;
    current_config_.password = password;
    anonymous_mode_ = false;

    disconnect();
    return connect(current_config_);
}

bool MQTTClient::isAnonymousMode() const {
    return anonymous_mode_;
}

// ============================================
// SEQUENCE NUMBER (Correlation-ID support)
// ============================================
uint32_t MQTTClient::getNextSeq() {
    return ++publish_seq_;
}

uint32_t MQTTClient::getCurrentSeq() const {
    return publish_seq_;
}

String MQTTClient::getBootTelemetrySequenceId() const {
    time_t unix_timestamp = timeManager.getUnixTimestamp();
    bool time_valid = timeManager.isSynchronized();
    ensureBootTelemetryInitialized(unix_timestamp, time_valid);
    return g_boot_sequence_id;
}

uint32_t MQTTClient::getPublishOutboxNoncriticalDropCount() const {
#ifndef MQTT_USE_PUBSUBCLIENT
    return g_publish_outbox_noncritical_drops.load();
#else
    return 0;
#endif
}

uint32_t MQTTClient::getPublishOutboxFullCount() const {
#ifndef MQTT_USE_PUBSUBCLIENT
    return g_publish_outbox_full_count.load();
#else
    return 0;
#endif
}

uint32_t MQTTClient::getSafePublishRetryCount() const {
    return safe_publish_retry_count_;
}

PublishFailureReasonClass MQTTClient::getLastPublishFailureReasonClass() const {
    return last_publish_failure_reason_;
}

const char* MQTTClient::getLastPublishFailureReasonClassName() const {
    return publishFailureReasonClassToString(last_publish_failure_reason_);
}

// ============================================
// PUBLISHING (WITH CIRCUIT BREAKER)
// ============================================
#ifndef MQTT_USE_PUBSUBCLIENT
bool MQTTClient::shouldApplyRuntimeCriticalPublishPace_(const String& topic) const {
    if (topic.indexOf("/system/intent_outcome/lifecycle") >= 0) {
        return false;
    }
    return isRealtimeResponsePublishTopic(topic) || isIntentOutcomePublishTopic(topic);
}

bool MQTTClient::deferRuntimeCriticalPublishPace_(const String& topic,
                                                const String& payload,
                                                uint8_t qos,
                                                bool critical,
                                                PublishFailureReasonClass* set_reason) {
    if (!shouldApplyRuntimeCriticalPublishPace_(topic)) {
        return false;
    }

    const unsigned long now_ms = millis();
    if (last_runtime_critical_publish_ms_ == 0UL) {
        return false;
    }

    const unsigned long next_allowed_ms =
        last_runtime_critical_publish_ms_ + RUNTIME_CRITICAL_PUBLISH_INTER_PACE_MS;
    if (now_ms >= next_allowed_ms) {
        return false;
    }

    const unsigned long defer_ms = next_allowed_ms - now_ms;
    IntentMetadata metadata =
        extractIntentMetadataFromPayload(payload.c_str(), critical ? "critical_pub_pace" : "pub_pace");
    const PublishQueueEnqueueResult pq =
        tryQueuePublish(topic.c_str(), payload.c_str(), qos, false, critical, &metadata, defer_ms);
    if (pq == PublishQueueEnqueueResult::Enqueued) {
        if (set_reason != nullptr) {
            *set_reason = PublishFailureReasonClass::None;
        }
        static unsigned long s_last_runtime_pace_log_ms = 0UL;
        if (s_last_runtime_pace_log_ms == 0UL ||
            (now_ms - s_last_runtime_pace_log_ms) >= 2000UL) {
            s_last_runtime_pace_log_ms = now_ms;
            LOG_D(TAG, String("[AUT-484] Runtime publish paced defer_ms=") + String(defer_ms) +
                           " topic=" + topic);
        }
        return true;
    }

    if (set_reason != nullptr) {
        *set_reason = mapQueueEnqueueResultToFailureReason(pq);
    }
    return false;
}

void MQTTClient::markRuntimeCriticalPublishCompleted_(const String& topic) {
    if (shouldApplyRuntimeCriticalPublishPace_(topic)) {
        last_runtime_critical_publish_ms_ = millis();
    }
}
#endif

bool MQTTClient::publish(const String& topic, const String& payload, uint8_t qos) {
    auto set_reason = [this](PublishFailureReasonClass reason) {
        last_publish_failure_reason_ = reason;
    };

    if (test_publish_hook_) {
        test_publish_hook_(topic, payload);
        set_reason(PublishFailureReasonClass::None);
        return true;
    }

    // Circuit Breaker: block publishes when broker is persistently down
    if (!circuit_breaker_.allowRequest()) {
        LOG_W(TAG, "MQTT publish blocked by Circuit Breaker (Service DOWN)");
        set_reason(PublishFailureReasonClass::CircuitBreakerOpen);
        return false;
    }

    // Registration Gate: block non-heartbeat publishes until server confirms registration
    bool is_heartbeat = topic.indexOf("/system/heartbeat") != -1 &&
                        topic.indexOf("/heartbeat/ack") == -1;
    // Keep terminal acknowledgements flowing even before registration ACK:
    // otherwise frontend intents can timeout although firmware executed command.
    bool is_actuator_response = topic.indexOf("/actuator/") != -1 &&
                                topic.indexOf("/response") != -1;
    bool is_sensor_response = topic.indexOf("/sensor/") != -1 &&
                              topic.indexOf("/response") != -1;
    bool is_system_response = topic.indexOf("/config_response") != -1 ||
                              topic.indexOf("/zone/ack") != -1 ||
                              topic.indexOf("/subzone/ack") != -1 ||
                              topic.indexOf("/system/command/response") != -1 ||
                              is_actuator_response ||
                              is_sensor_response;
    bool is_error_publish = topic.indexOf("/error") != -1;

    if (!registration_confirmed_ && !is_heartbeat && !is_system_response && !is_error_publish) {
        if (registration_start_ms_ > 0 &&
            (millis() - registration_start_ms_) > REGISTRATION_TIMEOUT_MS) {
            if (!registration_timeout_logged_) {
                LOG_W(TAG, "Registration timeout - gate remains CLOSED until valid heartbeat ACK (fail-closed)");
                registration_timeout_logged_ = true;
            }
            logAdmissionCorrelationBlockedPublish(topic, payload, "REGISTRATION_TIMEOUT");
            LOG_D(TAG, "Publish blocked (registration timeout, no ACK yet): " + topic);
            set_reason(PublishFailureReasonClass::TransportError);
            return false;
        } else {
            logAdmissionCorrelationBlockedPublish(topic, payload, "REGISTRATION_PENDING");
            LOG_D(TAG, "Publish blocked (awaiting registration): " + topic);
            set_reason(PublishFailureReasonClass::TransportError);
            return false;
        }
    }

    if (payload.length() == 0) {
        LOG_E(TAG, "Empty payload blocked for topic: " + topic);
        errorTracker.logCommunicationError(ERROR_MQTT_PAYLOAD_INVALID,
                                           ("Empty payload for: " + topic).c_str());
        set_reason(PublishFailureReasonClass::TransportError);
        return false;
    }

#ifndef MQTT_USE_PUBSUBCLIENT
    const bool critical_for_pace = isCriticalPublishTopic(topic);
    if (deferRuntimeCriticalPublishPace_(topic, payload, qos, critical_for_pace, nullptr)) {
        set_reason(PublishFailureReasonClass::None);
        return true;
    }
#endif

#ifndef MQTT_USE_PUBSUBCLIENT
    if (mqtt_client_ == nullptr) {
        LOG_W(TAG, "MQTT client not initialized, dropping message: " + topic);
        set_reason(PublishFailureReasonClass::TransportError);
        return false;
    }

    // M3: If called from Core 1 (Safety-Task), route through publish queue (Core 1 → Core 0).
    // Additionally, never publish directly from MQTT_EVENT_DATA callback context on Core 0:
    // this avoids re-entrant MQTT/newlib paths while inside esp_mqtt_task.
    if (xPortGetCoreID() == 1 || g_in_mqtt_event_callback.load()) {
        bool critical = isCriticalPublishTopic(topic);
        IntentMetadata metadata = extractIntentMetadataFromPayload(payload.c_str(), critical ? "critical_pub" : "pub");
        // AUT-344: tryQueuePublish distinguishes AUT-55 shed from hard failures.
        // Shed / non-critical enqueue misses must NOT trip the MQTT circuit breaker
        // (misclassified as broker-down), which previously amplified disconnects under burst.
        PublishQueueEnqueueResult pq = tryQueuePublish(topic.c_str(),
                                                       payload.c_str(),
                                                       qos,
                                                       false,
                                                       critical,
                                                       &metadata);
        if (pq == PublishQueueEnqueueResult::Enqueued) {
            circuit_breaker_.recordSuccess();
            set_reason(PublishFailureReasonClass::None);
            return true;
        }
        if (pq == PublishQueueEnqueueResult::ShedBackpressure) {
            LOG_D(TAG, "[AUT-344] Publish shed (COMM backpressure), not a CB failure: " + topic);
            set_reason(mapQueueEnqueueResultToFailureReason(pq));
            return false;
        }
        // Failed: queue full, oversize, null, or queue not initialised
        if (!critical) {
            LOG_W(TAG, "Publish queue enqueue failed (non-critical): " + topic);
            set_reason(mapQueueEnqueueResultToFailureReason(pq));
            return false;
        }
        // Queue enqueue failures are local backpressure (Core handoff), not transport proof.
        // Do not open MQTT circuit breaker here; reserve CB failures for real MQTT transport errors.
        LOG_W(TAG, "Publish queue enqueue failed (critical, no CB failure): " + topic);
        set_reason(mapQueueEnqueueResultToFailureReason(pq));
        return false;
    }

    // Core 0: direct publish via ESP-IDF (thread-safe internally).
    //
    // IMPORTANT for actuator responsiveness:
    // Direct publish is "fast path" only while the system is healthy. Under queue pressure,
    // even critical direct publishes can block inside esp_mqtt_client_publish().
    // That blocking steals time from near-realtime actuator feedback/response handling.
    //
    // Therefore, once pressure crosses the shed watermark, we reroute critical direct traffic
    // back into the queue path. This keeps control flow non-blocking from the caller's view
    // and avoids long synchronous stalls in the comm loop.
    //
    // In short:
    // - healthy transport: direct path keeps latency low
    // - pressured/degraded transport: queue path protects realtime behavior
    const bool critical_direct = isCriticalPublishTopic(topic);
    const bool realtime_response_direct = isRealtimeResponsePublishTopic(topic);
    if (critical_direct && !realtime_response_direct) {
        const PublishQueuePressureStats pq_stats = getPublishQueuePressureStats();
        if (pq_stats.fill_level >= PUBLISH_QUEUE_SHED_WATERMARK) {
            IntentMetadata metadata =
                extractIntentMetadataFromPayload(payload.c_str(), "critical_pub_defer");
            PublishQueueEnqueueResult pq = tryQueuePublish(topic.c_str(),
                                                           payload.c_str(),
                                                           qos,
                                                           false,
                                                           true,
                                                           &metadata);
            if (pq == PublishQueueEnqueueResult::Enqueued) {
                // Enqueued = accepted for async processing; caller is not blocked on socket I/O.
                // #region agent log
                LOG_W(TAG, String("[DBG5126ae] direct critical deferred to queue fill=") +
                                String(pq_stats.fill_level) +
                                " watermark=" + String(PUBLISH_QUEUE_SHED_WATERMARK) +
                                " topic=" + topic);
                // #endregion
                set_reason(PublishFailureReasonClass::None);
                return true;
            }
            if (pq == PublishQueueEnqueueResult::ShedBackpressure) {
                // Explicit shed under pressure: prefer dropping lower-value traffic over
                // risking long blocking calls that hurt control responsiveness.
                LOG_D(TAG, "[DBG5126ae] direct critical shed by queue pressure: " + topic);
                set_reason(mapQueueEnqueueResultToFailureReason(pq));
                return false;
            }
            LOG_W(TAG, "Direct critical defer enqueue failed, fallback to direct publish: " + topic);
        }
    }

    // Returns msg_id > 0 (QoS 1 queued), 0 (QoS 0 sent), -1 (error), -2 (outbox full).
    // PKG-16: pass explicit payload length so IDF skips its internal strlen()
    // on a possibly-NULL c_str() buffer (observed failure mode under OOM).
    const unsigned long direct_publish_started_ms = millis();
    int msg_id = esp_mqtt_client_publish(
        mqtt_client_,
        topic.c_str(),
        payload.c_str(),
        static_cast<int>(payload.length()),
        qos,
        0        // retain = false (avoid stale state on broker)
    );
    const unsigned long direct_publish_duration_ms = millis() - direct_publish_started_ms;
    if (direct_publish_duration_ms > 200UL) {
        // #region agent log
        LOG_W(TAG, String("[DBG5126ae] direct publish call slow duration_ms=") +
                        String(direct_publish_duration_ms) +
                        " msg_id=" + String(msg_id) +
                        " qos=" + String(qos) +
                        " core=" + String(xPortGetCoreID()) +
                        " in_callback=" + String(g_in_mqtt_event_callback.load() ? 1 : 0) +
                        " mqtt_connected=" + String(g_mqtt_connected.load() ? 1 : 0) +
                        " wifi_connected=" + String(WiFi.isConnected() ? 1 : 0) +
                        " topic=" + topic);
        // #endregion
    }

    if (msg_id >= 0) {
        circuit_breaker_.recordSuccess();
        set_reason(PublishFailureReasonClass::None);
        if (qos > 0) {
            g_qos1_enqueue_count.fetch_add(1);
            // [OUTBOX+1]: QoS-1 message entered IDF OUTBOX — stays there until PUBACK.
            // Counting these vs [OUTBOX-1] PUBACK events reveals accumulation rate.
            char pub_log[128];
            snprintf(pub_log, sizeof(pub_log),
                     "[OUTBOX+1] QoS-%u enqueued msg_id=%d heap=%u topic=%.60s",
                     (unsigned)qos, msg_id, (unsigned)ESP.getFreeHeap(), topic.c_str());
            LOG_D(TAG, pub_log);
        } else {
            LOG_D(TAG, "Published [msg_id=" + String(msg_id) + "]: " + topic);
        }
        markRuntimeCriticalPublishCompleted_(topic);
        return true;
    } else if (msg_id == -2) {
        uint32_t full_count = g_publish_outbox_full_count.fetch_add(1) + 1;
        // [FIX5-VERIFY] Serial confirms outbox-full events with heap + counter so we
        // can verify CONFIG_MQTT_OUTBOX_SIZE_BYTES reduces this count under burst load.
        {
            char outbox_log[112];
            snprintf(outbox_log, sizeof(outbox_log),
                     "[FIX5-VERIFY] OUTBOX full #%u topic=%.60s heap=%u",
                     (unsigned)full_count, topic.c_str(), (unsigned)ESP.getFreeHeap());
            LOG_W(TAG, outbox_log);
        }
        // AUT-390: OUTBOX full = ESP-seitiger Backpressure (TCP-Buffer voll oder IDF-Queue erschoepft).
        // Das ist KEIN Broker-Ausfall — der Broker ist erreichbar, aber der ESP kann momentan
        // nicht mehr senden. recordFailure() hier wuerde den CB in ~250ms oeffnen (5 Failures
        // bei 50ms-Takt) und den Heartbeat blockieren → Broker-Keepalive-Timeout (90s).
        // Echter Broker-Ausfall landet als MQTT_EVENT_DISCONNECTED → recordFailure() dort.
        // Avoid recursive publishIntentOutcome when the failing publish IS intent_outcome
        // (publishIntentOutcome already persists to NVS on publish failure).
        if (isCriticalPublishTopic(topic) && topic.indexOf("/system/intent_outcome") < 0) {
            IntentMetadata metadata = extractIntentMetadataFromPayload(payload.c_str(), "pub");
            // PKG-16: build reason string via snprintf on a stack buffer instead of
            // Arduino String concat. We are already in the OUTBOX-FULL path where
            // heap pressure is likely — another `String("...") + topic` concat can
            // silently allocate-fail and leave a buffer that downstream strncpy
            // dereferences as NULL (historical LoadProhibited signature).
            char reason_buf[192];
            snprintf(reason_buf, sizeof(reason_buf),
                     "ESP-IDF MQTT outbox full: %s",
                     topic.c_str());
            reason_buf[sizeof(reason_buf) - 1] = '\0';
            publishIntentOutcome("publish",
                                 metadata,
                                 "failed",
                                 "PUBLISH_OUTBOX_FULL",
                                 String(reason_buf),
                                 true);
        } else if (topic.indexOf("/system/intent_outcome") >= 0) {
            LOG_W(TAG, "intent_outcome publish hit outbox full — NVS replay path handles persistence");
        } else {
            uint32_t drop_cnt = g_publish_outbox_noncritical_drops.fetch_add(1) + 1;
            char drop_log[128];
            snprintf(drop_log, sizeof(drop_log),
                     "[OUTBOX-TRACE] OUTBOX full, non-crit drop #%u topic=%.60s heap=%u",
                     (unsigned)drop_cnt, topic.c_str(), (unsigned)ESP.getFreeHeap());
            LOG_D(TAG, drop_log);
        }
        set_reason(PublishFailureReasonClass::OutboxFull);
        return false;
    } else {
        // msg_id == -1: error (not connected or internal failure)
        // Don't count as failure if we're not connected (pre-connection publish attempt)
        if (g_mqtt_connected.load()) {
            circuit_breaker_.recordFailure();
            LOG_E(TAG, "Publish failed (connected but error): " + topic);
            errorTracker.logCommunicationError(ERROR_MQTT_PUBLISH_FAILED,
                                               ("Publish failed: " + topic).c_str());
        } else {
            LOG_W(TAG, "Publish before MQTT connected, dropping: " + topic);
        }
        set_reason(PublishFailureReasonClass::TransportError);
        return false;
    }

#else
    // PubSubClient path
    if (!isConnected()) {
        LOG_W(TAG, "MQTT not connected, adding to offline buffer");
        circuit_breaker_.recordFailure();
        set_reason(PublishFailureReasonClass::TransportError);
        return addToOfflineBuffer(topic, payload, qos);
    }

    bool success = mqtt_.publish(topic.c_str(), payload.c_str(), false);

    if (success) {
        circuit_breaker_.recordSuccess();
        set_reason(PublishFailureReasonClass::None);
        LOG_D(TAG, "Published: " + topic);
    } else {
        circuit_breaker_.recordFailure();
        LOG_E(TAG, "Publish failed: " + topic);
        errorTracker.logCommunicationError(ERROR_MQTT_PUBLISH_FAILED,
                                           ("Publish failed: " + topic).c_str());
        set_reason(PublishFailureReasonClass::TransportError);
        if (circuit_breaker_.isOpen()) {
            LOG_W(TAG, "Circuit Breaker OPENED after failure threshold");
        }
        addToOfflineBuffer(topic, payload, qos);
    }

    return success;
#endif
}

bool MQTTClient::safePublish(const String& topic, const String& payload, uint8_t qos, uint8_t retries) {
    const uint8_t max_attempts = static_cast<uint8_t>(retries) + 1;
    const bool critical = isCriticalPublishTopic(topic);

    for (uint8_t attempt = 0; attempt < max_attempts; ++attempt) {
        if (circuit_breaker_.isOpen()) {
            if (attempt == 0 && critical) {
                LOG_D(TAG, "SafePublish: CB OPEN, critical topic — single attempt");
                return publish(topic, payload, qos);
            }
            LOG_D(TAG, "SafePublish: CB OPEN, aborting after " +
                       String(attempt) + "/" + String(max_attempts) + " attempts");
            return false;
        }

        if (publish(topic, payload, qos)) {
            if (attempt > 0) {
                LOG_D(TAG, "SafePublish: OK on attempt " +
                           String(attempt + 1) + "/" + String(max_attempts));
            }
            return true;
        }

#ifndef MQTT_USE_PUBSUBCLIENT
        // Queue handoff failures (Core1 or MQTT callback context) are local backpressure.
        // Retrying immediately amplifies queue pressure and log storms without transport gain.
        if (xPortGetCoreID() == 1 || g_in_mqtt_event_callback.load()) {
            const PublishQueuePressureStats pq_stats = getPublishQueuePressureStats();
            if (pq_stats.fill_level >= PUBLISH_QUEUE_SIZE) {
                uint32_t abort_count = g_safe_publish_backpressure_abort_count.fetch_add(1) + 1;
                static unsigned long s_last_backpressure_abort_log_ms = 0;
                const unsigned long now_ms = millis();
                if (s_last_backpressure_abort_log_ms == 0UL ||
                    (now_ms - s_last_backpressure_abort_log_ms) >= 2000UL) {
                    s_last_backpressure_abort_log_ms = now_ms;
                    LOG_W(TAG, "SafePublish: abort retries due local queue backpressure fill=" +
                               String(pq_stats.fill_level) + "/" + String(PUBLISH_QUEUE_SIZE) +
                               " abort_count=" + String(abort_count));
                }
                break;
            }
        }
#endif

        if (attempt + 1 >= max_attempts) {
            break;
        }

        safe_publish_retry_count_++;

        // Exponential backoff: 50 / 100 / 200 / 250(cap) ms + 0..31ms jitter
        unsigned long backoff_ms = 50UL << (attempt > 3 ? 3 : attempt);
        if (backoff_ms > 250) backoff_ms = 250;
        backoff_ms += (esp_random() & 0x1FU);
        vTaskDelay(pdMS_TO_TICKS(backoff_ms));
    }

    LOG_W(TAG, "SafePublish failed after " + String(max_attempts) +
               " attempts: " + topic);
    return false;
}

// ============================================
// SUBSCRIPTION
// ============================================
bool MQTTClient::subscribe(const String& topic, uint8_t qos) {
#ifndef MQTT_USE_PUBSUBCLIENT
    if (mqtt_client_ == nullptr) {
        LOG_E(TAG, "Cannot subscribe, MQTT client not initialized");
        return false;
    }
    // esp_mqtt_client_subscribe is only effective when connected.
    // Called from on_connect_callback_ (after MQTT_EVENT_CONNECTED) — this is correct.
    int msg_id = esp_mqtt_client_subscribe(mqtt_client_, topic.c_str(), qos);
    if (msg_id >= 0) {
        LOG_I(TAG, "Subscribe sent (QoS " + String(qos) + "): " + topic);
        return true;
    } else {
        LOG_E(TAG, "Subscribe failed: " + topic);
        errorTracker.logCommunicationError(ERROR_MQTT_SUBSCRIBE_FAILED,
                                           ("Subscribe failed: " + topic).c_str());
        return false;
    }
#else
    if (!isConnected()) {
        LOG_E(TAG, "Cannot subscribe, MQTT not connected");
        errorTracker.logCommunicationError(ERROR_MQTT_SUBSCRIBE_FAILED,
                                           "Cannot subscribe, not connected");
        return false;
    }

    bool success = mqtt_.subscribe(topic.c_str(), qos);

    if (success) {
        LOG_I(TAG, "Subscribed (QoS " + String(qos) + "): " + topic);
    } else {
        LOG_E(TAG, "Subscribe failed: " + topic);
        errorTracker.logCommunicationError(ERROR_MQTT_SUBSCRIBE_FAILED,
                                           ("Subscribe failed: " + topic).c_str());
    }
    return success;
#endif
}

bool MQTTClient::queueSubscribe(const String& topic, uint8_t qos, bool critical) {
#ifndef MQTT_USE_PUBSUBCLIENT
    return enqueueSubscription_(topic, qos, critical);
#else
    (void)critical;
    return subscribe(topic, qos);
#endif
}

void MQTTClient::requestBootstrapHeartbeatAfterAck() {
#ifndef MQTT_USE_PUBSUBCLIENT
    bootstrap_heartbeat_pending_ = true;
    bootstrap_heartbeat_send_pending_ = false;
    bootstrap_ack_subscription_ready_ = false;
    bootstrap_config_subscription_ready_ = false;
    pending_bootstrap_ack_subscribe_msg_id_ = -1;
    pending_bootstrap_config_subscribe_msg_id_ = -1;
#endif
}

#ifndef MQTT_USE_PUBSUBCLIENT
bool MQTTClient::enqueueSubscription_(const String& topic, uint8_t qos, bool critical, bool front) {
    if (topic.length() == 0) {
        return false;
    }

    for (uint8_t i = 0; i < pending_subscription_count_; ++i) {
        if (pending_subscriptions_[i].topic == topic) {
            if (qos > pending_subscriptions_[i].qos) {
                pending_subscriptions_[i].qos = qos;
            }
            pending_subscriptions_[i].critical = pending_subscriptions_[i].critical || critical;
            if (front && i > 0) {
                PendingSubscription existing = pending_subscriptions_[i];
                for (int j = i; j > 0; --j) {
                    pending_subscriptions_[j] = pending_subscriptions_[j - 1];
                }
                pending_subscriptions_[0] = existing;
            }
            return true;
        }
    }

    if (pending_subscription_count_ >= MAX_PENDING_SUBSCRIPTIONS) {
        LOG_E(TAG, "Subscription queue full, dropping topic: " + topic);
        errorTracker.logCommunicationError(ERROR_MQTT_SUBSCRIBE_FAILED,
                                           ("Subscription queue full: " + topic).c_str());
        return false;
    }

    PendingSubscription sub;
    sub.topic = topic;
    sub.qos = qos;
    sub.attempts = 0;
    sub.critical = critical;
    sub.next_attempt_ms = millis();

    if (front) {
        for (int j = pending_subscription_count_; j > 0; --j) {
            pending_subscriptions_[j] = pending_subscriptions_[j - 1];
        }
        pending_subscriptions_[0] = sub;
    } else {
        pending_subscriptions_[pending_subscription_count_] = sub;
    }

    pending_subscription_count_++;
    return true;
}

void MQTTClient::clearSubscriptionQueue_() {
    pending_subscription_count_ = 0;
    pending_bootstrap_ack_subscribe_msg_id_ = -1;
    pending_bootstrap_config_subscribe_msg_id_ = -1;
    bootstrap_ack_subscription_ready_ = false;
    bootstrap_config_subscription_ready_ = false;
}
#endif

bool MQTTClient::unsubscribe(const String& topic) {
#ifndef MQTT_USE_PUBSUBCLIENT
    if (mqtt_client_ == nullptr) return false;
    int msg_id = esp_mqtt_client_unsubscribe(mqtt_client_, topic.c_str());
    if (msg_id >= 0) {
        LOG_I(TAG, "Unsubscribed from: " + topic);
        return true;
    }
    LOG_E(TAG, "Unsubscribe failed: " + topic);
    return false;
#else
    if (!isConnected()) {
        LOG_W(TAG, "Cannot unsubscribe, MQTT not connected");
        return false;
    }
    bool success = mqtt_.unsubscribe(topic.c_str());
    if (success) {
        LOG_I(TAG, "Unsubscribed from: " + topic);
    } else {
        LOG_E(TAG, "Unsubscribe failed: " + topic);
    }
    return success;
#endif
}

void MQTTClient::setCallback(std::function<void(const String&, const String&)> callback) {
    message_callback_ = callback;
}

// ============================================
// MONITORING / LOOP
// ============================================
void MQTTClient::loop() {
    if (!initialized_) {
        return;
    }

#ifndef MQTT_USE_PUBSUBCLIENT
    // ESP-IDF has its own MQTT task — no manual mqtt_.loop() or reconnect() needed here.
    // loop() handles: NTP time sync + staged subscribe recovery + periodic heartbeat
    // + managed reconnect jitter to avoid multi-device reconnect herding.
    timeManager.loop();
    processManagedReconnect_();
    processSubscriptionQueue();
    processBootstrapHeartbeatAfterSubscribe();
    publishHeartbeat();
#else
    // PubSubClient path: handle time sync, MQTT maintenance, heartbeat, and reconnect.
    timeManager.loop();

    if (isConnected()) {
        mqtt_.loop();
        publishHeartbeat();
    } else {
        handleDisconnection();
    }
#endif
}

#ifndef MQTT_USE_PUBSUBCLIENT
void MQTTClient::processBootstrapHeartbeatAfterSubscribe() {
    if (!bootstrap_heartbeat_send_pending_) {
        return;
    }

    if (!g_mqtt_connected.load()) {
        // Keep pending until reconnect callback resets/arms the proper bootstrap path.
        return;
    }

    publishHeartbeat(true);
    bootstrap_heartbeat_send_pending_ = false;
    LOG_I(TAG, "[SYNC] Bootstrap heartbeat sent after SUBSCRIBED (deferred to loop)");
}

unsigned long MQTTClient::computeReconnectJitterMs_(uint16_t attempt) const {
    const unsigned long capped_attempt = (attempt > 6U) ? 6U : static_cast<unsigned long>(attempt);
    const unsigned long exp_backoff = MANAGED_RECONNECT_BASE_DELAY_MS << capped_attempt;
    const unsigned long bounded_backoff = (exp_backoff > MANAGED_RECONNECT_MAX_DELAY_MS)
                                              ? MANAGED_RECONNECT_MAX_DELAY_MS
                                              : exp_backoff;

    unsigned long entropy = static_cast<unsigned long>(esp_random() & 0x3FFU);  // 0..1023
    if (g_system_config.esp_id.length() > 0) {
        entropy ^= static_cast<unsigned long>(g_system_config.esp_id.charAt(g_system_config.esp_id.length() - 1));
    }
    const unsigned long jitter = entropy % 650U;  // 0..649ms
    return bounded_backoff + jitter;
}

void MQTTClient::scheduleManagedReconnect_(const char* reason, unsigned long base_delay_ms) {
    if (g_mqtt_connected.load()) {
        next_managed_reconnect_ms_ = 0;
        managed_reconnect_attempts_ = 0;
        return;
    }
    if (manual_reconnect_suspended_) {
        return;
    }

    const unsigned long now = millis();
    const unsigned long minimum_delay = (base_delay_ms > MANAGED_RECONNECT_MAX_DELAY_MS)
                                            ? MANAGED_RECONNECT_MAX_DELAY_MS
                                            : base_delay_ms;
    const unsigned long computed_delay =
        computeReconnectJitterMs_(managed_reconnect_attempts_ > 0 ? managed_reconnect_attempts_ : 1);
    const unsigned long delay_ms = (computed_delay < minimum_delay) ? minimum_delay : computed_delay;
    next_managed_reconnect_ms_ = now + delay_ms;

    // #region agent log
    LOG_W(TAG, String("[DBG5126ae] reconnect schedule request now=") + String(now) +
                   " next=" + String(next_managed_reconnect_ms_) +
                   " reason=" + String(reason != nullptr ? reason : "unknown") +
                   " base_delay=" + String(base_delay_ms) +
                   " computed_delay=" + String(computed_delay) +
                   " attempts=" + String(managed_reconnect_attempts_) +
                   " last_disconnect=" + String(last_disconnect_ms_) +
                   " last_errno=" + String(last_transport_errno_));
    // #endregion

    LOG_W(TAG, String("[INC-EA5484] managed reconnect scheduled in ") + String(delay_ms) +
                   "ms (attempt=" + String(managed_reconnect_attempts_) +
                   ", reason=" + String(reason != nullptr ? reason : "unknown") +
                   ", write_timeouts=" + String(transport_write_timeout_count_) +
                   ", tls_timeouts=" + String(tls_connect_timeout_count_) +
                   ", tcp_errors_other=" + String(tcp_transport_error_count_) +
                   ", last_errno=" + String(last_transport_errno_) + ")");
}

void MQTTClient::processManagedReconnect_() {
    if (g_mqtt_connected.load()) {
        next_managed_reconnect_ms_ = 0;
        managed_reconnect_attempts_ = 0;
        last_disconnect_ms_ = 0;
        manual_reconnect_suspended_ = false;
        return;
    }
    // [AUT-676] Zeit-Watchdog: if TCP-SYN hangs after reconnect()→ESP_OK and IDF emits no
    // DISCONNECTED/ERROR event, is_connecting_ stays true forever → Dead-State. Force-clear.
    if (is_connecting_ && is_connecting_since_ms_ > 0 &&
        millis() - is_connecting_since_ms_ > MANAGED_RECONNECT_CONNECTING_WATCHDOG_MS) {
        LOG_W(TAG, "[AUT-676] is_connecting_ watchdog expired — force-clear, retry reconnect");
        is_connecting_ = false;
        is_connecting_since_ms_ = 0;
    }
    // [AUT-656-A] TLS handshake in-flight after reconnect() → ESP_OK. Block further
    // reconnect() calls until MQTT_EVENT_CONNECTED or MQTT_EVENT_DISCONNECTED clears this.
    if (is_connecting_) return;
    if (mqtt_client_ == nullptr) {
        // [AUT-570] After hard_reset_connect_failed mqtt_client_ is nullptr but a
        // scheduled reconnect timer may be active. Don't clear the timer — attempt
        // connect() when it fires so recovery can proceed without a Hardware-Reboot.
        if (next_managed_reconnect_ms_ > 0 && millis() >= next_managed_reconnect_ms_) {
            next_managed_reconnect_ms_ = 0;
            ++managed_reconnect_attempts_;  // [AUT-656-C] counter must be symmetric with non-nullptr path
            if (managed_reconnect_attempts_ > 5) {
                // connect() itself keeps failing (e.g. OOM): extended backoff, no silent loop.
                LOG_E(TAG, String("[AUT-656-C] nullptr connect failed >5x — reset + extended backoff"));
                managed_reconnect_attempts_ = 0;
                scheduleManagedReconnect_("nullptr_max_retry", MANAGED_RECONNECT_MAX_DELAY_MS);
                return;
            }
            bool ok = connect(current_config_);
            if (!ok) {
                scheduleManagedReconnect_("nullptr_reconnect_retry",
                                         MANAGED_RECONNECT_WRITE_TIMEOUT_BOOST_MS);
            }
        }
        return;
    }
    if (manual_reconnect_suspended_) {
        return;
    }

    if (next_managed_reconnect_ms_ == 0 || millis() < next_managed_reconnect_ms_) {
        return;
    }

    // Avoid issuing reconnect requests immediately after disconnect to prevent
    // reconnect-race amplification while WiFi/transport are still settling.
    if (last_disconnect_ms_ > 0) {
        unsigned long now = millis();
        unsigned long grace_until = last_disconnect_ms_ + MANAGED_RECONNECT_AUTO_GRACE_MS;
        if (now < grace_until) {
            next_managed_reconnect_ms_ = grace_until;
            LOG_I(TAG, "[INC-EA5484] managed reconnect deferred (auto-reconnect grace)");
            return;
        }
    }

    ++managed_reconnect_attempts_;
    // #region agent log
    LOG_W(TAG, String("[DBG5126ae] reconnect attempt gate now=") + String(millis()) +
                   " next=" + String(next_managed_reconnect_ms_) +
                   " last_disconnect=" + String(last_disconnect_ms_) +
                   " attempts=" + String(managed_reconnect_attempts_) +
                   " write_timeouts=" + String(transport_write_timeout_count_) +
                   " tls_timeouts=" + String(tls_connect_timeout_count_) +
                   " tcp_errors_other=" + String(tcp_transport_error_count_) +
                   " last_errno=" + String(last_transport_errno_));
    // #endregion

    if (managed_reconnect_attempts_ > 5) {
        /* AUT-539/AUT-555 — Hard-Reset: destroy+reinit instead of stop+start.
         *
         * Root cause of the 4+ hour post-disconnect silence on a field device:
         *
         *   The previous code called esp_mqtt_client_stop() + esp_mqtt_client_start()
         *   after 5 failed soft-reconnects. This reused the existing MQTT client handle
         *   and its internal transport list. Every failed TCP connect attempt leaves one
         *   lwIP PCB in TIME_WAIT state for 60–120 seconds. With a default pool of ~16
         *   PCBs, 5 failed attempts × 2 TIME_WAIT sockets each = pool exhausted.
         *   Once the pool is full, lwip_socket() returns ENOMEM and
         *   esp_transport_connect() silently fails — no TCP SYN packet ever leaves the
         *   device, so the broker log shows no connection attempt at all.
         *
         * Fix: call connect(current_config_) instead.
         *   connect() internally calls esp_mqtt_client_stop() + esp_mqtt_client_destroy()
         *   + esp_mqtt_client_init() + esp_mqtt_client_start(). The destroy+init cycle
         *   allocates a fresh esp_mqtt_client_handle_t, re-registers our event handler,
         *   and starts with a clean lwIP socket context — all TIME_WAIT PCBs from the
         *   previous handle are abandoned and the pool is effectively released.
         *   connect() also resets managed_reconnect_attempts_ internally (we reset it
         *   here before the call so the counter is 0 if connect() itself fails).
         *
         * Threshold > 5: conservative — at 5 attempts the PCB pool is typically still
         *   half-free, so we trigger the hard-reset before it actually runs dry. */
        LOG_W(TAG, String("[AUT-539] Hard-Reset MQTT-Client nach ") + String(managed_reconnect_attempts_) +
                       " Soft-Reconnect-Versuchen (destroy+reinit)");
        LOG_W(TAG, String("[AUT-555-D1] before connect heap=") +
                       String((int)heap_caps_get_free_size(MALLOC_CAP_DEFAULT)) +
                       " tasks=" + String((int)uxTaskGetNumberOfTasks()) +
                       " attempt=" + String(managed_reconnect_attempts_));
        managed_reconnect_attempts_ = 0;
        bool ok = connect(current_config_);
        LOG_W(TAG, String("[AUT-555-D1] after connect ok=") + String(ok ? 1 : 0) +
                       " heap=" + String((int)heap_caps_get_free_size(MALLOC_CAP_DEFAULT)) +
                       " tasks=" + String((int)uxTaskGetNumberOfTasks()));
        if (!ok) {
            // connect() itself failed (e.g. OOM at esp_mqtt_client_init time).
            // Schedule another managed reconnect with the write-timeout boost interval
            // so we don't spin immediately but still retry.
            scheduleManagedReconnect_("hard_reset_connect_failed", MANAGED_RECONNECT_WRITE_TIMEOUT_BOOST_MS);
        }
        // On success: MQTT_EVENT_CONNECTED fires asynchronously and clears reconnect state.
        return;
    }

    esp_err_t err = esp_mqtt_client_reconnect(mqtt_client_);
    if (err != ESP_OK) {
        LOG_W(TAG, String("[INC-EA5484] managed reconnect request failed: ") + esp_err_to_name(err));
        // ESP_FAIL: client->state != MQTT_STATE_WAIT_RECONNECT (vendor Z.1641).
        // Normally blocked by is_connecting_ guard above; reaching here means the
        // client entered a non-WAIT state without us setting is_connecting_=true.
        // Reschedule so the hard-reset path (attempts > 5) can eventually fire.
        manual_reconnect_suspended_ = false;
        next_managed_reconnect_ms_ = 0;
        scheduleManagedReconnect_("reconnect_request_failed", MANAGED_RECONNECT_WRITE_TIMEOUT_BOOST_MS);
        LOG_W(TAG, "[INC-EA5484] reconnect failed -> retry scheduled via managed backoff");
        return;
    }

    LOG_I(TAG, String("[INC-EA5484] managed reconnect requested (attempt=") +
               String(managed_reconnect_attempts_) + ")");
    is_connecting_ = true;             // [AUT-656-A] TLS handshake now in-flight; block reconnect() calls
    is_connecting_since_ms_ = millis();  // [AUT-676] watchdog start
    scheduleManagedReconnect_("awaiting_connect_event");
}

void MQTTClient::processSubscriptionQueue() {
    if (!g_mqtt_connected.load() || mqtt_client_ == nullptr || pending_subscription_count_ == 0) {
        return;
    }

    PendingSubscription& sub = pending_subscriptions_[0];
    unsigned long now = millis();
    if (now < sub.next_attempt_ms) {
        return;
    }

    int msg_id = esp_mqtt_client_subscribe(mqtt_client_, sub.topic.c_str(), sub.qos);
    if (msg_id >= 0) {
        LOG_I(TAG, "Subscribe sent (QoS " + String(sub.qos) + "): " + sub.topic);
        bool is_ack_topic = sub.topic.indexOf("/system/heartbeat/ack") != -1;
        bool is_config_topic = sub.topic.endsWith("/config");

        for (uint8_t i = 1; i < pending_subscription_count_; ++i) {
            pending_subscriptions_[i - 1] = pending_subscriptions_[i];
        }
        pending_subscription_count_--;

        // Defer bootstrap heartbeat until MQTT_EVENT_SUBSCRIBED for required lanes.
        // Sending immediately after esp_mqtt_client_subscribe() races the broker: the first
        // server config push can be published before /config is active → ESP waits until retry.
        if (is_ack_topic && bootstrap_heartbeat_pending_) {
            pending_bootstrap_ack_subscribe_msg_id_ = msg_id;
            LOG_I(TAG, "[SYNC] Bootstrap heartbeat deferred until SUBSCRIBED (msg_id=" + String(msg_id) + ")");
        }
        if (is_config_topic && bootstrap_heartbeat_pending_) {
            pending_bootstrap_config_subscribe_msg_id_ = msg_id;
            LOG_I(TAG, "[SYNC] Bootstrap heartbeat waiting for config SUBSCRIBED (msg_id=" + String(msg_id) + ")");
        }
        // AUT-484 F1: Pace remaining bootstrap subscriptions to protect keepalive/TCP.
        if (pending_subscription_count_ > 0) {
            pending_subscriptions_[0].next_attempt_ms = millis() + SUBSCRIPTION_INTER_PACE_MS;
        }
        return;
    }

    sub.attempts++;
    unsigned long backoff = SUBSCRIBE_RETRY_BASE_MS << (sub.attempts > 4 ? 4 : sub.attempts);
    if (backoff > SUBSCRIBE_RETRY_MAX_MS) {
        backoff = SUBSCRIBE_RETRY_MAX_MS;
    }
    sub.next_attempt_ms = now + backoff;

    if (sub.attempts >= MAX_SUBSCRIBE_RETRIES) {
        String failed_topic = sub.topic;
        bool critical = sub.critical;
        uint8_t qos = sub.qos;
        for (uint8_t i = 1; i < pending_subscription_count_; ++i) {
            pending_subscriptions_[i - 1] = pending_subscriptions_[i];
        }
        pending_subscription_count_--;
        LOG_E(TAG, "Subscribe failed permanently after retries: " + failed_topic);
        errorTracker.logCommunicationError(ERROR_MQTT_SUBSCRIBE_FAILED,
                                           ("Subscribe failed permanently: " + failed_topic).c_str());
        if (critical) {
            enqueueSubscription_(failed_topic, qos, true, true);
        }
        return;
    }

    LOG_W(TAG, "Subscribe retry " + String(sub.attempts) + "/" + String(MAX_SUBSCRIBE_RETRIES) +
               " scheduled in " + String(backoff) + "ms: " + sub.topic);
}
#endif

// ============================================
// M3: PUBLISH QUEUE DRAIN (Core 0 only)
// ============================================
#ifndef MQTT_USE_PUBSUBCLIENT

// Helper: Check if topic is sensor_data (for AUT-6 retry logic)
static bool isSensorDataTopic(const String& topic) {
    return topic.indexOf("/sensor_data/") != -1 || topic.indexOf("/sensor/") != -1;
}

// Helper: Get backoff delay in ms for retry attempt (100ms → 500ms → 1000ms)
static uint32_t getRetryBackoffMs(uint8_t attempt) {
    static const uint32_t backoff_delays[] = { 100, 500, 1000 };
    if (attempt >= 3) return 1000;
    return backoff_delays[attempt];
}

// Drain limit per communication tick to avoid publish micro-bursts that can
// saturate the TCP write path (observed as errno=11 under load).
// AUT-54: Drain at most one queued publish per comm-task tick by default — was 3, which stacked
// multiple esp_mqtt_client_publish calls in one loop iteration and amplified TCP write
// pressure during rapid actuator ON/OFF + sensor/heartbeat traffic.
// AUT-481 P3: Adaptive boost to 2/tick when fill>=3 and transport is healthy (see policy helper).
static constexpr uint8_t MAX_PRESSURE_DEFER_PER_MESSAGE = 3;

void MQTTClient::processPublishQueue() {
    if (mqtt_client_ == nullptr) return;
    if (g_publish_queue == NULL) return;
    if (isPublishQueuePaused()) return;
    if (!g_mqtt_connected.load() || !WiFi.isConnected()) {
        static unsigned long s_last_drain_skip_disconnected_log_ms = 0;
        const unsigned long now = millis();
        if (s_last_drain_skip_disconnected_log_ms == 0UL ||
            (now - s_last_drain_skip_disconnected_log_ms) >= 5000UL) {
            s_last_drain_skip_disconnected_log_ms = now;
            // #region agent log
            LOG_W(TAG, String("[DBG5126ae] processPublishQueue skipped disconnected mqtt_connected=") +
                            String(g_mqtt_connected.load() ? 1 : 0) +
                            " wifi_connected=" + String(WiFi.isConnected() ? 1 : 0));
            // #endregion
        }
        return;
    }

    // AUT-359: Drain-Admission-Symmetrie zur publish()-Pfad-Logik.
    //
    // Vorher: processPublishQueue() rief esp_mqtt_client_publish() ohne
    // CB-Check auf — Drain transportierte trotz OPEN, waehrend neue
    // publish()-Aufrufe (Heartbeat, Core-0-Direkt) am CB sofort scheiterten
    // (siehe AUT-346 / S3-recovery-pfad-2026-05-12 §5).
    //
    // Jetzt: Drain skippt vollstaendig, solange der MQTT-CircuitBreaker OPEN
    // ist. Das schuetzt die ESP-IDF-Outbox (AUT-326-Crash-Pfad) und die
    // TCP-Schicht (errno=11/EAGAIN) waehrend persistenter Broker-Ausfaelle.
    // allowRequest() liefert in HALF_OPEN automatisch true (max. 10 s
    // Test-Fenster) — der Recovery-Probe passiert also ohne Sondercode.
    // Queue-Wachstum ist gewollt: bestehende Mechanismen greifen
    // (Shedding ab WATERMARK 6, intent_outcome-NVS-Replay, queue_pressure
    // Hysterese). intent_outcome-Outbox wurde oben bereits prozessiert,
    // damit Replay-Fluss bei OPEN nicht haengen bleibt.
    if (!circuit_breaker_.allowRequest()) {
        static unsigned long last_cb_drain_log_ms = 0;
        unsigned long now = millis();
        if (now - last_cb_drain_log_ms > 5000) {
            last_cb_drain_log_ms = now;
            LOG_D(TAG, "[OUTBOX-TRACE] Drain skipped: MQTT Circuit Breaker OPEN");
        }
        return;
    }
    processIntentOutcomeOutbox();

    const uint8_t queue_fill_at_tick =
        static_cast<uint8_t>(uxQueueMessagesWaiting(g_publish_queue));
    const uint8_t drain_budget = computeAdaptivePublishDrainBudget(
        queue_fill_at_tick,
        transport_write_timeout_count_ > 0,
        circuit_breaker_.allowRequest(),
        isPublishQueuePaused());

    // AUT-117-fix: Write-timeout drain guard.
    // After a write timeout on this connection, esp_mqtt_client_publish() can block
    // again on the same degraded socket. If we continue draining here, we accumulate
    // latency exactly when actuator feedback should stay responsive.
    //
    // So we pause drain until reconnect completes, then resume cleanly.
    // Counter reset happens in MQTT_EVENT_CONNECTED.
    if (transport_write_timeout_count_ > 0) {
        static unsigned long s_drain_wt_guard_log_ms = 0;
        const unsigned long drain_guard_now_ms = millis();
        if (s_drain_wt_guard_log_ms == 0UL ||
            (drain_guard_now_ms - s_drain_wt_guard_log_ms) >= 5000UL) {
            s_drain_wt_guard_log_ms = drain_guard_now_ms;
            // #region agent log
            LOG_W(TAG, String("[DBG5126ae] drain skipped write timeout degraded wt_count=") +
                           String(transport_write_timeout_count_));
            // #endregion
        }
        return;
    }

    static PublishRequest req;
    unsigned long now_ms = millis();
    uint8_t drained_this_tick = 0;

    while (drained_this_tick < drain_budget &&
           xQueueReceive(g_publish_queue, &req, 0) == pdTRUE) {
        if (now_ms < req.next_retry_ms) {
            if (xQueueSend(g_publish_queue, &req, 0) != pdTRUE) {
                LOG_W(TAG, "Publish retry queue full during backoff, dropping: " + String(req.topic));
                g_publish_outbox_noncritical_drops.fetch_add(1);
            }
            break;
        }

        // AUT-368: registration-gated queue drain
        // Runtime evidence (run 20260515_142347, H93/H22) shows a 4.1s blocking
        // esp_mqtt_client_publish call in queue-drain while registration was not
        // yet confirmed (reg_confirmed=0), immediately followed by transport timeout
        // and MQTT disconnect. Mirror the direct publish() admission rule here.
        if (!registration_confirmed_) {
            req.next_retry_ms = now_ms + 1000UL;
            if (xQueueSend(g_publish_queue, &req, 0) != pdTRUE) {
                LOG_W(TAG, "Publish defer queue full while registration pending, dropping: " + String(req.topic));
                g_publish_outbox_noncritical_drops.fetch_add(1);
            } else {
                // #region agent log
                LOG_W(TAG, String("[DBG5126ae] queue drain deferred registration pending next_retry_ms=") +
                                String(req.next_retry_ms) +
                                " topic=" + String(req.topic) +
                                " mqtt_connected=" + String(g_mqtt_connected.load() ? 1 : 0));
                // #endregion
            }
            break;
        }

        const bool critical_topic = req.critical;
        const bool realtime_response_topic = isRealtimeResponsePublishTopic(String(req.topic));
        const bool intent_outcome_topic = isIntentOutcomePublishTopic(String(req.topic));
        const uint8_t queue_fill_before_publish =
            static_cast<uint8_t>(uxQueueMessagesWaiting(g_publish_queue));
        if (critical_topic &&
            !realtime_response_topic &&
            !intent_outcome_topic &&
            queue_fill_before_publish >= PUBLISH_QUEUE_SHED_WATERMARK) {
            // Keep this defer bounded. Unbounded requeue at high fill can keep the queue hot
            // indefinitely and starve non-critical sensor publishes after reconnect.
            if (req.pressure_defer_count < MAX_PRESSURE_DEFER_PER_MESSAGE) {
                req.pressure_defer_count++;
                req.next_retry_ms = now_ms + 1000UL;
                if (xQueueSend(g_publish_queue, &req, 0) != pdTRUE) {
                    LOG_W(TAG, "Publish defer queue full under pressure (critical), dropping: " + String(req.topic));
                    g_publish_outbox_noncritical_drops.fetch_add(1);
                } else {
                    // #region agent log
                    LOG_W(TAG, String("[DBG5126ae] queue drain deferred critical under pressure fill=") +
                                    String(queue_fill_before_publish) +
                                    " watermark=" + String(PUBLISH_QUEUE_SHED_WATERMARK) +
                                    " defer_count=" + String(req.pressure_defer_count) +
                                    " next_retry_ms=" + String(req.next_retry_ms) +
                                    " topic=" + String(req.topic));
                    // #endregion
                }
                break;
            }

            LOG_W(TAG, String("[DBG5126ae] forcing critical drain publish after pressure defers topic=") +
                           String(req.topic) +
                           " fill=" + String(queue_fill_before_publish) +
                           " defer_count=" + String(req.pressure_defer_count));
        }

        const String req_topic = String(req.topic);
        if (shouldApplyRuntimeCriticalPublishPace_(req_topic)) {
            const unsigned long next_allowed_ms =
                last_runtime_critical_publish_ms_ + RUNTIME_CRITICAL_PUBLISH_INTER_PACE_MS;
            if (last_runtime_critical_publish_ms_ > 0UL && now_ms < next_allowed_ms) {
                req.next_retry_ms = next_allowed_ms;
                if (xQueueSend(g_publish_queue, &req, 0) != pdTRUE) {
                    LOG_W(TAG, "Runtime publish pace requeue failed, dropping: " + req_topic);
                    g_publish_outbox_noncritical_drops.fetch_add(1);
                }
                break;
            }
        }

        const bool mqtt_connected_before_call = g_mqtt_connected.load();
        const bool wifi_connected_before_call = WiFi.isConnected();
        if (!mqtt_connected_before_call || !wifi_connected_before_call) {
            // #region agent log
            LOG_W(TAG, String("[DBG5126ae] queue drain publish invoked disconnected mqtt_before=") +
                            String(mqtt_connected_before_call ? 1 : 0) +
                            " wifi_before=" + String(wifi_connected_before_call ? 1 : 0) +
                            " qos=" + String(req.qos) +
                            " topic=" + String(req.topic));
            // #endregion
            req.next_retry_ms = now_ms + 1000UL;
            if (xQueueSend(g_publish_queue, &req, 0) != pdTRUE) {
                LOG_W(TAG, "Publish defer queue full while disconnected, dropping: " + String(req.topic));
                g_publish_outbox_noncritical_drops.fetch_add(1);
            } else {
                // #region agent log
                LOG_W(TAG, String("[DBG5126ae] queue drain deferred disconnected next_retry_ms=") +
                                String(req.next_retry_ms) +
                                " topic=" + String(req.topic));
                // #endregion
            }
            break;
        }
        const unsigned long drain_publish_started_ms = millis();
        int msg_id = esp_mqtt_client_publish(
            mqtt_client_,
            req.topic,
            req.payload,
            0,
            req.qos,
            req.retain ? 1 : 0
        );
        const unsigned long drain_publish_duration_ms = millis() - drain_publish_started_ms;
        const bool mqtt_connected_after_call = g_mqtt_connected.load();
        const bool wifi_connected_after_call = WiFi.isConnected();
        if (drain_publish_duration_ms > 200UL) {
            const unsigned long registration_age_ms =
                (registration_start_ms_ > 0) ? (millis() - registration_start_ms_) : 0UL;
            // #region agent log
            LOG_W(TAG, String("[DBG5126ae] queue drain publish call slow duration_ms=") +
                            String(drain_publish_duration_ms) +
                            " msg_id=" + String(msg_id) +
                            " qos=" + String(req.qos) +
                            " core=" + String(xPortGetCoreID()) +
                            " mqtt_before=" + String(mqtt_connected_before_call ? 1 : 0) +
                            " wifi_before=" + String(wifi_connected_before_call ? 1 : 0) +
                            " mqtt_after=" + String(mqtt_connected_after_call ? 1 : 0) +
                            " wifi_after=" + String(wifi_connected_after_call ? 1 : 0) +
                            " reg_confirmed=" + String(registration_confirmed_ ? 1 : 0) +
                            " registration_age_ms=" + String(registration_age_ms) +
                            " topic=" + String(req.topic));
            // #endregion
        }
        drained_this_tick++;
        if (msg_id >= 0) {
            // AUT-359: Drain-Feedback-Symmetrie zu publish() Z. 708:
            // erfolgreiche Drain-Publishes treiben CB Richtung CLOSED
            // (Recovery aus HALF_OPEN). Vorher fehlte dieser Pfad ganz —
            // Drain-Erfolge wurden vom CB nicht registriert.
            circuit_breaker_.recordSuccess();
            req.pressure_defer_count = 0;
            markRuntimeCriticalPublishCompleted_(req_topic);
            continue;
        }

        // Queue-drain path can also hit OUTBOX full — count and log separately from
        // the direct publish() path so both sources are visible in the serial trace.
        if (msg_id == -2) {
            uint32_t cnt = g_publish_outbox_full_count.fetch_add(1) + 1;
            char q_log[128];
            snprintf(q_log, sizeof(q_log),
                     "[OUTBOX-TRACE][QUEUE] OUTBOX full #%u topic=%.60s heap=%u",
                     (unsigned)cnt, req.topic, (unsigned)ESP.getFreeHeap());
            LOG_W(TAG, q_log);
            // AUT-390: OUTBOX full im Drain-Pfad = gleicher Backpressure-Grund wie im
            // Direktpfad (publish() AUT-390-Fix) — recordFailure() entfernt.
            // Die Retry-Logik weiter unten (should_retry) behandelt OUTBOX-full korrekt:
            // kritische Messages werden bis 3× wiederholt, Sensor-Data ggf. gesheddet.
            // CB-Failure nur bei echtem Broker-Ausfall (MQTT_EVENT_DISCONNECTED).
        } else if (msg_id == -1) {
            // AUT-359: Drain-Feedback-Symmetrie zu publish() Z. 765-776 —
            // -1 ist „connected but error“; nur dann CB-Failure zaehlen,
            // wenn aktuell verbunden. Ohne Verbindung waere es ein
            // Pre-Connection-Drop und sollte CB nicht eskalieren.
            if (g_mqtt_connected.load()) {
                circuit_breaker_.recordFailure();
            }
        }

        bool is_sensor_data = isSensorDataTopic(String(req.topic));
        const char* drop_code = (msg_id == -2) ? "PUBLISH_OUTBOX_FULL" : "EXECUTE_FAIL";
        String drop_reason = String("Publish dropped for topic ") + String(req.topic);

        // AUT-55: Under queue pressure (fill >= watermark), only retry critical messages.
        // Non-critical sensor_data retries are shed to preserve queue headroom.
        uint8_t queue_fill = static_cast<uint8_t>(uxQueueMessagesWaiting(g_publish_queue));
        bool under_pressure = (queue_fill >= PUBLISH_QUEUE_SHED_WATERMARK);
        bool connected_now = g_mqtt_connected.load();
        bool transport_backpressure = isWritePathTimeoutErrno(last_transport_errno_);

        bool should_retry = (req.critical && req.attempt < 3) ||
                           (is_sensor_data && req.attempt < 3 &&
                            !under_pressure &&
                            connected_now &&
                            !transport_backpressure);

        if (should_retry) {
            req.attempt++;
            uint32_t backoff_ms = getRetryBackoffMs(req.attempt - 1);
            req.next_retry_ms = now_ms + backoff_ms;

            LOG_D(TAG, "Publish retry scheduled (attempt " + String(req.attempt) + "/3, " +
                       String(backoff_ms) + "ms backoff): " + String(req.topic));

            if (xQueueSend(g_publish_queue, &req, 0) != pdTRUE) {
                LOG_W(TAG, "Publish retry queue full, dropping: " + String(req.topic));
                errorTracker.logCommunicationError(ERROR_MQTT_PUBLISH_FAILED,
                                                   ("Publish retry queue full: " + String(req.topic)).c_str());
                if (req.critical) {
                    publishIntentOutcome("publish",
                                         req.metadata,
                                         "failed",
                                         "QUEUE_FULL",
                                         "Critical publish retry queue full",
                                         true);
                } else if (is_sensor_data) {
                    g_publish_outbox_noncritical_drops.fetch_add(1);
                }
            }
            continue;
        }

        LOG_W(TAG, String("Publish dropped") +
              (under_pressure && is_sensor_data ? " (backpressure shed)" : " after retries") +
              ": " + String(req.topic));
        errorTracker.logCommunicationError(ERROR_MQTT_PUBLISH_FAILED,
                                           ("Publish failed: " + String(req.topic)).c_str());

        if (is_sensor_data) {
            g_publish_outbox_noncritical_drops.fetch_add(1);
        }

        if (req.critical) {
            publishIntentOutcome("publish",
                                 req.metadata,
                                 "failed",
                                 drop_code,
                                 drop_reason,
                                 true);
        }
    }
}

#endif

#ifndef MQTT_USE_PUBSUBCLIENT
bool MQTTClient::publishSessionAnnounce(uint32_t epoch) {
    if (mqtt_client_ == nullptr) {
        return false;
    }

    char topic[128];
    snprintf(topic, sizeof(topic), "kaiser/god/esp/%s/session/announce", g_system_config.esp_id.c_str());
    topic[sizeof(topic) - 1] = '\0';

    time_t unix_timestamp = timeManager.getUnixTimestamp();
    bool time_valid = timeManager.isSynchronized();
    ensureBootTelemetryInitialized(unix_timestamp, time_valid);
    unsigned long boot_ts = g_segment_start_ts;
    if (boot_ts == 0) {
        boot_ts = (unix_timestamp > 0) ? static_cast<unsigned long>(unix_timestamp) : (millis() / 1000UL);
    }

    const char* announce_reason = epoch > 1 ? "reconnect" : "boot";
    uint64_t ts_ms = timeManager.getUnixTimestampMs();
    if (ts_ms == 0) {
        ts_ms = static_cast<uint64_t>(millis());
    }

    char payload[320];
    snprintf(payload,
             sizeof(payload),
             "{\"esp_id\":\"%s\",\"handover_epoch\":%lu,\"session_epoch\":%lu,"
             "\"reason\":\"%s\",\"ts_ms\":%llu,\"boot_ts\":\"%lu\"}",
             g_system_config.esp_id.c_str(),
             static_cast<unsigned long>(epoch),
             static_cast<unsigned long>(epoch),
             announce_reason,
             static_cast<unsigned long long>(ts_ms),
             boot_ts);
    payload[sizeof(payload) - 1] = '\0';

    const int msg_id = esp_mqtt_client_publish(
        mqtt_client_,
        topic,
        payload,
        0,
        0,  // AUT-54: QoS 0 — same backpressure rationale as actuator telemetry
        0   // retain = false
    );

    if (msg_id < 0) {
        pending_session_announce_msg_id_ = -1;
        LOG_W(TAG, String("[INC-EA5484] session/announce publish failed epoch=") + String(epoch));
        return false;
    }

    pending_session_announce_msg_id_ = msg_id;
    LOG_I(TAG, String("[INC-EA5484] session/announce published epoch=") + String(epoch));
    return true;
}
#endif

// ============================================
// STATUS GETTERS
// ============================================
String MQTTClient::getConnectionStatus() {
#ifndef MQTT_USE_PUBSUBCLIENT
    return g_mqtt_connected.load() ? "Connected" : "Disconnected";
#else
    if (mqtt_.connected()) {
        return "Connected";
    }
    switch (mqtt_.state()) {
        case MQTT_CONNECTION_TIMEOUT:    return "Connection timeout";
        case MQTT_CONNECTION_LOST:       return "Connection lost";
        case MQTT_CONNECT_FAILED:        return "Connect failed";
        case MQTT_DISCONNECTED:          return "Disconnected";
        case MQTT_CONNECT_BAD_PROTOCOL:  return "Bad protocol";
        case MQTT_CONNECT_BAD_CLIENT_ID: return "Bad client ID";
        case MQTT_CONNECT_UNAVAILABLE:   return "Server unavailable";
        case MQTT_CONNECT_BAD_CREDENTIALS: return "Bad credentials";
        case MQTT_CONNECT_UNAUTHORIZED:  return "Unauthorized";
        default: return "Unknown (" + String(mqtt_.state()) + ")";
    }
#endif
}

uint16_t MQTTClient::getConnectionAttempts() const {
#ifndef MQTT_USE_PUBSUBCLIENT
    return 0;  // ESP-IDF manages reconnect internally; not exposed.
#else
    return reconnect_attempts_;
#endif
}

bool MQTTClient::hasOfflineMessages() const {
#ifndef MQTT_USE_PUBSUBCLIENT
    return false;  // ESP-IDF Outbox is opaque; individual message tracking not exposed.
#else
    return offline_buffer_count_ > 0;
#endif
}

uint16_t MQTTClient::getOfflineMessageCount() const {
#ifndef MQTT_USE_PUBSUBCLIENT
    return 0;
#else
    return offline_buffer_count_;
#endif
}

CircuitState MQTTClient::getCircuitBreakerState() const {
    return circuit_breaker_.getState();
}

uint8_t MQTTClient::getCircuitBreakerFailureCount() const {
    return circuit_breaker_.getFailureCount();
}

// ============================================
// HEARTBEAT SYSTEM
// ============================================
void MQTTClient::publishHeartbeat(bool force) {
    unsigned long current_time = millis();
    const unsigned long heartbeat_interval_ms =
        registration_confirmed_ ? HEARTBEAT_INTERVAL_MS : HEARTBEAT_REGISTRATION_RETRY_MS;

    if (!force && (current_time - last_heartbeat_ < heartbeat_interval_ms)) {
        return;
    }

    // Do not build/publish heartbeats while disconnected.
    // This reduces heap churn and retry pressure in reconnect windows,
    // including forced bootstrap heartbeat paths.
    if (!isConnected()) {
        return;
    }

    last_heartbeat_ = current_time;

    // M5.4: Heap monitoring — logged alongside every heartbeat for long-term leak detection.
    LOG_I("MEM", "[MEM] Free heap: " + String(ESP.getFreeHeap()) +
          " B, min free: " + String(ESP.getMinFreeHeap()) +
          " B, max alloc: " + String(ESP.getMaxAllocHeap()) + " B");

    const char* topic = TopicBuilder::buildSystemHeartbeatTopic();
    // TopicBuilder returns a shared static buffer; copy immediately so logs keep
    // the original heartbeat topic even if nested publishes overwrite the buffer.
    const String heartbeat_topic = String(topic);

    time_t unix_timestamp = timeManager.getUnixTimestamp();
    bool time_valid = timeManager.isSynchronized();
    ensureBootTelemetryInitialized(unix_timestamp, time_valid);

    String payload;
    // Keep heartbeat assembly deterministic and reduce heap fragmentation.
    // AUT-134: reserve close to observed payload size to avoid realloc churn
    // during reconnect/config bursts.
    payload.reserve(768);
    payload = "{";
    payload += "\"esp_id\":\"" + g_system_config.esp_id + "\",";
    payload += "\"zone_id\":\"" + g_kaiser.zone_id + "\",";
    payload += "\"master_zone_id\":\"" + g_kaiser.master_zone_id + "\",";
    payload += "\"zone_assigned\":" + String(g_kaiser.zone_assigned ? "true" : "false") + ",";
    payload += "\"ts\":" + String((unsigned long)unix_timestamp) + ",";
    payload += "\"time_valid\":" + String(time_valid ? "true" : "false") + ",";
    payload += "\"boot_sequence_id\":\"" + g_boot_sequence_id + "\",";
    payload += "\"reset_reason\":\"" + String(resetReasonToString(g_boot_reset_reason)) + "\",";
    payload += "\"segment_start_ts\":" + String(g_segment_start_ts) + ",";
    payload += "\"uptime\":" + String(millis() / 1000) + ",";
    payload += "\"heap_free\":" + String(ESP.getFreeHeap()) + ",";
    payload += "\"wifi_rssi\":" + String(WiFi.RSSI()) + ",";
    // [FIX5-VERIFY] firmware_version in core heartbeat — server can confirm which
    // firmware build is running without a separate API call or provisioning page.
    payload += "\"firmware_version\":\"" + String(KAISER_FIRMWARE_VERSION_STRING) + "\",";
    payload += "\"hardware_type\":\"" + String(HardwareConfig::HEARTBEAT_HARDWARE_TYPE) + "\",";
    payload += "\"sensor_count\":" + String(sensorManager.getActiveSensorCount()) + ",";
    payload += "\"actuator_count\":" + String(actuatorManager.getActiveActuatorCount()) + ",";
    // Expose active offline-rule count so server-side drift detection can
    // trigger a targeted config resync when rules were lost locally.
    payload += "\"offline_rule_count\":" + String(offlineModeManager.getOfflineRuleCount()) + ",";
    // AUT-716: Spool telemetry — lets frontend show badge when offline data is pending replay
    if (spoolManager.isEnabled()) {
        payload += "\"spool_pending_count\":" + String(spoolManager.pendingCount()) + ",";
        payload += "\"spool_dropped_count\":" + String(spoolManager.droppedCount()) + ",";
    }
    payload += "\"wifi_ip\":\"" + WiFi.localIP().toString() + "\",";

    // PKG-17: gpio_status removed from heartbeat (redundant with REST
    // GET /api/v1/devices/{id}/gpio-status and actuator/+/status).
    // Reclaims ~8.2 kB permanent heap via halved PUBLISH_PAYLOAD_MAX_LEN.

#ifndef ENABLE_METRICS_SPLIT
    payload += "\"metrics_schema_version\":" +
               String(OfflineModeManager::OFFLINE_AUTHORITY_METRICS_SCHEMA_VERSION) + ",";
    payload += "\"offline_enter_count\":" + String(offlineModeManager.getOfflineEnterCount()) + ",";
    payload += "\"adopting_enter_count\":" + String(offlineModeManager.getAdoptingEnterCount()) + ",";
    payload += "\"adoption_noop_count\":" + String(offlineModeManager.getAdoptionNoopCount()) + ",";
    payload += "\"adoption_delta_count\":" + String(offlineModeManager.getAdoptionDeltaCount()) + ",";
    payload += "\"handover_abort_count\":" + String(offlineModeManager.getHandoverAbortCount()) + ",";
    payload += "\"handover_contract_reject_count\":" +
               String(offlineModeManager.getHandoverContractRejectCount()) + ",";
    payload += "\"handover_contract_last_reject\":\"" +
               String(offlineModeManager.getLastHandoverContractRejectCode()) + "\",";
#endif
    payload += "\"active_handover_epoch\":" + String(offlineModeManager.getActiveHandoverEpoch()) + ",";
    payload += "\"handover_completed_epoch\":" + String(offlineModeManager.getHandoverCompletedEpoch()) + ",";
    // Heartbeat health: split "degraded" semantics — persistence drift vs FSM vs network CB
    // (Rule: do not overload a single "degraded" flag for unrelated subsystems.)
    {
        bool persistence_degraded = offlineModeManager.isPersistenceDriftActive();
        bool runtime_state_degraded = false;
        switch (g_system_config.current_state) {
            case STATE_CONFIG_PENDING_AFTER_RESET:
            case STATE_SAFE_MODE:
            case STATE_SAFE_MODE_PROVISIONING:
            case STATE_ERROR:
            case STATE_LIBRARY_DOWNLOADING:
                runtime_state_degraded = true;
                break;
            default:
                break;
        }
        bool mqtt_cb_open = circuit_breaker_.getState() == CircuitState::OPEN;
        bool wifi_cb_open = wifiManager.getCircuitBreakerState() == CircuitState::OPEN;
        bool network_degraded = mqtt_cb_open || wifi_cb_open;
        payload += "\"persistence_degraded\":" + String(persistence_degraded ? "true" : "false") + ",";
        payload += "\"persistence_degraded_reason\":\"" +
                   String(offlineModeManager.getLastPersistenceDriftReason()) + "\",";
        payload += "\"runtime_state_degraded\":" + String(runtime_state_degraded ? "true" : "false") + ",";
        payload += "\"mqtt_circuit_breaker_open\":" + String(mqtt_cb_open ? "true" : "false") + ",";
        payload += "\"wifi_circuit_breaker_open\":" + String(wifi_cb_open ? "true" : "false") + ",";
        payload += "\"network_degraded\":" + String(network_degraded ? "true" : "false") + ",";
    }
#ifndef MQTT_USE_PUBSUBCLIENT
    // [AUT-745] One-shot report of the previous disconnect's diagnosis — reaches
    // the server DB even when nobody has physical Serial access to the device,
    // which was the exact blind spot during the 2026-07-28 Klima Dante incident.
    if (last_disconnect_pending_report_) {
        payload += "\"last_disconnect_reason\":\"" + String(last_disconnect_reason_) + "\",";
        payload += "\"last_disconnect_rssi\":" + String(last_disconnect_rssi_) + ",";
        payload += "\"last_disconnect_wifi_connected\":" +
                   String(last_disconnect_wifi_connected_ ? "true" : "false") + ",";
        last_disconnect_pending_report_ = false;
    }
#endif
#ifndef ENABLE_METRICS_SPLIT
    payload += "\"persistence_drift_count\":" +
               String(offlineModeManager.getPersistenceDriftCount()) + ",";
    payload += "\"critical_outcome_drop_count\":" +
               String(getCriticalOutcomeDropCountTelemetry()) + ",";
    payload += "\"publish_outbox_drop_count\":" +
               String(getPublishOutboxNoncriticalDropCount()) + ",";
    payload += "\"publish_outbox_full_count\":" +
               String(getPublishOutboxFullCount()) + ",";
#ifndef MQTT_USE_PUBSUBCLIENT
    {
        PublishQueuePressureStats pq_stats = getPublishQueuePressureStats();
        payload += "\"publish_queue_fill\":" + String(pq_stats.fill_level) + ",";
        payload += "\"publish_queue_hwm\":" + String(pq_stats.high_watermark) + ",";
        payload += "\"publish_queue_shed_count\":" + String(pq_stats.shed_count) + ",";
        payload += "\"publish_queue_drop_count\":" + String(pq_stats.drop_count) + ",";
    }
#endif
    payload += "\"sensor_command_queue_overflow_count\":" +
               String(getSensorCommandQueueOverflowCount()) + ",";
    payload += "\"safe_publish_retry_count\":" +
               String(safe_publish_retry_count_) + ",";
    payload += "\"intent_chain_stage_enqueue_fail_count\":" +
               String(getIntentChainStageEnqueueFailCount()) + ",";
    payload += "\"emergency_rejected_no_token_total\":" +
               String(getEmergencyRejectedNoTokenCount()) + ",";
#endif
    payload += "\"config_status\":";
    payload += configManager.getDiagnosticsJSON();
    payload += "}";

    bool hb_ok = publish(heartbeat_topic, payload, 0);
    // #region agent log
    unsigned long ack_age_ms = 0;
#ifndef MQTT_USE_PUBSUBCLIENT
    if (g_last_server_ack_ms.load() > 0) {
        ack_age_ms = millis() - g_last_server_ack_ms.load();
    }
#endif
    LOG_W(TAG, String("[DBG5126ae] heartbeat publish state ok=") +
                   String(hb_ok ? 1 : 0) +
                   " reg_confirmed=" + String(registration_confirmed_ ? 1 : 0) +
                   " wifi_connected=" + String(WiFi.isConnected() ? 1 : 0) +
                   " rssi=" + String(WiFi.RSSI()) +
                   " ack_age_ms=" + String(ack_age_ms) +
                   // [AUT-745] Distinguishes WHY a heartbeat failed (CB open / queue-shed /
                   // outbox-full / transport-error / none) instead of just ok=0 — needed to
                   // tell Kandidat-D (Circuit-Breaker still OPEN post-reconnect) apart from
                   // Kandidat-B/C (silent transport failure) at the exact failure moment.
                   " fail_reason=" + String((int)last_publish_failure_reason_) +
                   " cb_state=" + String((int)circuit_breaker_.getState()) +
                   " cb_failures=" + String(circuit_breaker_.getFailureCount()));
    // #endregion
    if (!hb_ok) {
        LOG_W(TAG, "Heartbeat publish failed (topic=" + heartbeat_topic + ")");
    }

#ifdef ENABLE_METRICS_SPLIT
    publishHeartbeatMetrics();
#endif
}

// ============================================
// AUT-121: HEARTBEAT METRICS SPLIT
// ============================================
#ifdef ENABLE_METRICS_SPLIT
void MQTTClient::publishHeartbeatMetrics() {
    if (!registration_confirmed_ || !isConnected()) {
        return;
    }

    if (metrics_skip_count_ < 0xFF) {
        metrics_skip_count_++;
    }

    MetricsSnapshot current = {};
    current.publish_outbox_full_count = getPublishOutboxFullCount();
    current.offline_enter_count = offlineModeManager.getOfflineEnterCount();
    current.adopting_enter_count = offlineModeManager.getAdoptingEnterCount();
    current.adoption_noop_count = offlineModeManager.getAdoptionNoopCount();
    current.adoption_delta_count = offlineModeManager.getAdoptionDeltaCount();
    current.handover_abort_count = offlineModeManager.getHandoverAbortCount();
    current.handover_contract_reject_count = offlineModeManager.getHandoverContractRejectCount();
    current.persistence_drift_count = offlineModeManager.getPersistenceDriftCount();
    current.critical_outcome_drop_count = getCriticalOutcomeDropCountTelemetry();
    current.publish_outbox_drop_count = getPublishOutboxNoncriticalDropCount();
    current.sensor_cmd_queue_overflow_count = getSensorCommandQueueOverflowCount();
    current.safe_publish_retry_count = safe_publish_retry_count_;
    current.intent_chain_stage_enqueue_fail_count = getIntentChainStageEnqueueFailCount();
    current.emergency_rejected_no_token_total = getEmergencyRejectedNoTokenCount();

    bool changed = metricsChanged_(current);
    bool interval_reached = (metrics_skip_count_ >= METRICS_MAX_SKIP_COUNT);

    if (!changed && !interval_reached) {
        return;
    }

    metrics_skip_count_ = 0;
    last_metrics_ = current;

    const String metrics_topic = String(TopicBuilder::buildSystemHeartbeatMetricsTopic());

    String payload;
    payload.reserve(512);
    payload = "{";
    payload += "\"esp_id\":\"" + g_system_config.esp_id + "\",";
    payload += "\"ts\":" + String((unsigned long)timeManager.getUnixTimestamp()) + ",";
    payload += "\"metrics_schema_version\":" +
               String(OfflineModeManager::OFFLINE_AUTHORITY_METRICS_SCHEMA_VERSION) + ",";
    payload += "\"offline_enter_count\":" + String(current.offline_enter_count) + ",";
    payload += "\"adopting_enter_count\":" + String(current.adopting_enter_count) + ",";
    payload += "\"adoption_noop_count\":" + String(current.adoption_noop_count) + ",";
    payload += "\"adoption_delta_count\":" + String(current.adoption_delta_count) + ",";
    payload += "\"handover_abort_count\":" + String(current.handover_abort_count) + ",";
    payload += "\"handover_contract_reject_count\":" +
               String(current.handover_contract_reject_count) + ",";
    payload += "\"handover_contract_last_reject\":\"" +
               String(offlineModeManager.getLastHandoverContractRejectCode()) + "\",";
    payload += "\"persistence_drift_count\":" +
               String(current.persistence_drift_count) + ",";
    payload += "\"critical_outcome_drop_count\":" +
               String(current.critical_outcome_drop_count) + ",";
    payload += "\"publish_outbox_drop_count\":" +
               String(current.publish_outbox_drop_count) + ",";
    // [FIX5-VERIFY] publish_outbox_full_count: total msg_id==-2 outbox-full events.
    // Complements drop_count: critical topics escape via NVS replay so drop_count != full_count.
    payload += "\"publish_outbox_full_count\":" +
               String(current.publish_outbox_full_count) + ",";
#ifndef MQTT_USE_PUBSUBCLIENT
    {
        PublishQueuePressureStats pq_stats = getPublishQueuePressureStats();
        payload += "\"publish_queue_fill\":" + String(pq_stats.fill_level) + ",";
        payload += "\"publish_queue_hwm\":" + String(pq_stats.high_watermark) + ",";
        payload += "\"publish_queue_shed_count\":" + String(pq_stats.shed_count) + ",";
        payload += "\"publish_queue_drop_count\":" + String(pq_stats.drop_count) + ",";
    }
#endif
    payload += "\"sensor_command_queue_overflow_count\":" +
               String(current.sensor_cmd_queue_overflow_count) + ",";
    payload += "\"safe_publish_retry_count\":" +
               String(current.safe_publish_retry_count) + ",";
    payload += "\"intent_chain_stage_enqueue_fail_count\":" +
               String(current.intent_chain_stage_enqueue_fail_count) + ",";
    payload += "\"emergency_rejected_no_token_total\":" +
               String(current.emergency_rejected_no_token_total);
    payload += "}";

    publish(metrics_topic, payload, 0);
}

bool MQTTClient::metricsChanged_(const MetricsSnapshot& current) const {
    return memcmp(&current, &last_metrics_, sizeof(MetricsSnapshot)) != 0;
}
#endif  // ENABLE_METRICS_SPLIT

// ============================================
// REGISTRATION GATE (Bug #1 Fix)
// ============================================
bool MQTTClient::isRegistrationConfirmed() const {
    return registration_confirmed_;
}

void MQTTClient::confirmRegistration() {
    if (!registration_confirmed_) {
        registration_confirmed_ = true;
        registration_timeout_logged_ = false;
        LOG_I(TAG, "╔════════════════════════════════════════╗");
        LOG_I(TAG, "║  REGISTRATION CONFIRMED BY SERVER     ║");
        LOG_I(TAG, "╚════════════════════════════════════════╝");
        LOG_I(TAG, "Gate opened - publishes now allowed");
    }
}

bool MQTTClient::checkRegistrationTimeout() {
    if (registration_confirmed_) return true;
    if (registration_start_ms_ == 0) return false;
    if ((millis() - registration_start_ms_) > REGISTRATION_TIMEOUT_MS) {
        if (!registration_timeout_logged_) {
            LOG_W(TAG, "Registration timeout observed - waiting for explicit heartbeat ACK (gate stays closed)");
            registration_timeout_logged_ = true;
        }
    }
    return false;
}

void MQTTClient::setOnConnectCallback(std::function<void()> callback) {
    on_connect_callback_ = std::move(callback);
}

void MQTTClient::setTestPublishHook(std::function<void(const String&, const String&)> hook) {
    test_publish_hook_ = std::move(hook);
}

void MQTTClient::clearTestPublishHook() {
    test_publish_hook_ = nullptr;
}

// ============================================
// ESP-IDF MQTT EVENT HANDLER (SAFETY-RTOS M2)
// Runs in ESP-IDF MQTT task (Core 0, Priority 3 — below Safety-Task Priority 5).
// args = MQTTClient* instance (passed during esp_mqtt_client_register_event).
// ============================================
#ifndef MQTT_USE_PUBSUBCLIENT
void MQTTClient::mqtt_event_handler(void* args, esp_event_base_t base,
                                    int32_t event_id, void* event_data) {
    MQTTClient* self = static_cast<MQTTClient*>(args);
    esp_mqtt_event_handle_t event = static_cast<esp_mqtt_event_handle_t>(event_data);

    switch (event_id) {

        case MQTT_EVENT_BEFORE_CONNECT: {
            // AUT-593: Refresh LWT timestamp before every MQTT CONNECT packet.
            applyMqttRuntimeConfig(event->client, g_mqtt_runtime_task_stack);
            break;
        }

        case MQTT_EVENT_CONNECTED: {
            LOG_I(TAG, "╔════════════════════════════════════════╗");
            LOG_I(TAG, "║  MQTT_EVENT_CONNECTED                 ║");
            LOG_I(TAG, "╚════════════════════════════════════════╝");
            // [AUT-745] Symmetric to the [INC-EA5484] disconnect marker below — gives
            // a RSSI-at-connect baseline to diff against RSSI-at-disconnect for the
            // "Connected-but-Silent" defect (silence after CONNACK, no local error seen).
            LOG_I(TAG, String("[AUT-745] connect marker uptime_ms=") + String(millis()) +
                       " wifi_rssi=" + String(WiFi.RSSI()) +
                       " wifi_connected=" + String(WiFi.isConnected() ? "true" : "false"));
            // session_present=1 means the broker has a saved session from a prior
            // connection (clean_session=false). The broker will replay all pending
            // QoS-1 PUBREC/PUBCOMP state → OUTBOX fills immediately on reconnect.
            // This is the Session-Takeover-Replay vector observed in INC-OUTBOX-2026-05-10.
            LOG_I(TAG, String("[OUTBOX-TRACE] session_present=") +
                       String(event->session_present) +
                       " (1=broker replays pending QoS-1 state -> OUTBOX may pre-fill)");
            if (self->mqtt_client_ != nullptr) {
                const int runtime_outbox_bytes = esp_mqtt_client_get_outbox_size(self->mqtt_client_);
                LOG_I(TAG, String("[FIX2-VERIFY] IDF runtime outbox_size=") +
                           String(runtime_outbox_bytes) + " bytes");
                if (runtime_outbox_bytes > 0 && runtime_outbox_bytes <= 4096) {
                    LOG_W(TAG, "[AUT-477] OUTBOX at prebuilt default 4096 B — "
                               "sdkconfig.defaults inactive (Arduino libmqtt.a); "
                               "paced actuator bursts risk queue/outbox pressure");
                }
            }

            // Update shared connection state (atomic — read by Safety-Task Core 1)
            g_mqtt_connected.store(true);

            // SAFETY-P1 Race-Fix (Bug-2): reset ACK timestamp immediately after
            // marking connected, before on_connect_callback_ is invoked.
            // Without this, Safety-Task (Core 1) can read isConnected()==true with
            // the stale pre-reconnect timestamp (~209 s ago in the observed failure)
            // and incorrectly trigger the 120 s ACK-timeout path in that narrow
            // ~ms window before on_connect_callback_ reaches its own reset.
            g_last_server_ack_ms.store(millis());

            // Reset Registration Gate
            self->registration_confirmed_ = false;
            self->registration_start_ms_  = millis();
            self->registration_timeout_logged_ = false;
            self->clearSubscriptionQueue_();
            self->bootstrap_heartbeat_pending_ = false;
            self->pending_bootstrap_ack_subscribe_msg_id_ = -1;
            self->pending_bootstrap_config_subscribe_msg_id_ = -1;
            self->bootstrap_ack_subscription_ready_ = false;
            self->bootstrap_config_subscription_ready_ = false;
            self->bootstrap_heartbeat_send_pending_ = false;
            self->next_managed_reconnect_ms_ = 0;
            self->managed_reconnect_attempts_ = 0;
            self->is_connecting_ = false;  // [AUT-656-A] TLS handshake complete
            self->manual_reconnect_suspended_ = false;
            self->last_runtime_critical_publish_ms_ = 0UL;

            // PKG-18: Capture write-timeout history before counter reset.
            // Used below to decide post-reconnect queue stabilization duration.
            const uint32_t prior_write_timeouts = self->transport_write_timeout_count_;

            self->transport_write_timeout_count_ = 0;
            self->tls_connect_timeout_count_ = 0;
            self->tcp_transport_error_count_ = 0;
            self->last_transport_errno_ = 0;
            self->last_disconnect_ms_ = 0;
            self->pending_session_announce_msg_id_ = -1;
#ifdef ENABLE_METRICS_SPLIT
            self->metrics_skip_count_ = METRICS_MAX_SKIP_COUNT;
#endif

            // AUT-69 Step 1: Hold queue drain until session/announce is acknowledged
            // or guard timeout unblocks progress.
            // PKG-18: Extend hold when reconnecting after write-timeout instability
            // to let transport stabilize before draining queued publishes.
            {
                uint32_t announce_guard_ms = 300;
                if (prior_write_timeouts >= WRITE_TIMEOUT_ESCALATION_THRESHOLD) {
                    announce_guard_ms = POST_RECONNECT_TRANSPORT_SETTLE_MS;
                    LOG_I(TAG, String("[PKG-18] transport recovery hold ") +
                               String(announce_guard_ms) + "ms (prior_write_timeouts=" +
                               String(prior_write_timeouts) + ")");
                }
                // #region agent log
                LOG_W(TAG, String("[DBG5126ae] reconnect hold decision prior_write_timeouts=") +
                               String(prior_write_timeouts) +
                               " threshold=" + String(WRITE_TIMEOUT_ESCALATION_THRESHOLD) +
                               " guard_ms=" + String(announce_guard_ms));
                // #endregion
                pauseForAnnounceAck(announce_guard_ms);
            }
            uint32_t announce_epoch = offlineModeManager.getActiveHandoverEpoch();
            if (offlineModeManager.getMode() == OfflineMode::OFFLINE_ACTIVE) {
                announce_epoch++;
            }
            if (announce_epoch == 0) {
                announce_epoch = 1;
            }
            self->publishSessionAnnounce(announce_epoch);

            // Circuit Breaker: connection success resets failure counter
            self->circuit_breaker_.recordSuccess();

            // SAFETY-P1 Mechanisms A + D + E:
            // on_connect_callback_ = onMqttConnectCallback() in main.cpp
            //   → subscribeToAllTopics() (Mechanism A: 11 subscriptions)
            //   → g_last_server_ack_ms reset (Mechanism D reset — second reset, harmless)
            //   → publishAllActuatorStatus() + publishHeartbeat(true) on reconnect (Mechanism E)
            //   → offlineModeManager.onReconnect() (SAFETY-P4)
            if (self->on_connect_callback_) {
                self->on_connect_callback_();
            }
            break;
        }

        case MQTT_EVENT_DISCONNECTED:
            LOG_W(TAG, "╔════════════════════════════════════════╗");
            LOG_W(TAG, "║  MQTT_EVENT_DISCONNECTED              ║");
            LOG_W(TAG, "╚════════════════════════════════════════╝");

            // INC-2026-04-11-ea5484-mqtt-transport-keepalive (PKG-01):
            // Telemetrie-Marker mit uptime + free heap + WiFi-RSSI, damit Disconnect-
            // Ursache bei naechstem HW-Repro (Broker-Timeout vs. Socket-Stall vs.
            // WLAN-Drop) ohne weiteren Code-Druck korreliert werden kann.
            LOG_W(TAG, String("[INC-EA5484] disconnect marker uptime_ms=") +
                       String(millis()) +
                       " free_heap=" + String(ESP.getFreeHeap()) +
                       " wifi_rssi=" + String(WiFi.RSSI()) +
                       " wifi_connected=" + String(WiFi.isConnected() ? "true" : "false"));

            // Update shared connection state
            g_mqtt_connected.store(false);

            // Reset Registration Gate
            self->registration_confirmed_ = false;
            self->registration_start_ms_  = 0;
            self->registration_timeout_logged_ = false;
            self->clearSubscriptionQueue_();
            self->bootstrap_heartbeat_pending_ = false;
            self->pending_bootstrap_ack_subscribe_msg_id_ = -1;
            self->pending_bootstrap_config_subscribe_msg_id_ = -1;
            self->bootstrap_ack_subscription_ready_ = false;
            self->bootstrap_config_subscription_ready_ = false;
            self->bootstrap_heartbeat_send_pending_ = false;
            self->pending_session_announce_msg_id_ = -1;
            resumeAfterAnnounceAck("guard_timeout");
            self->is_connecting_ = false;  // [AUT-656-A] TLS failed or transport dropped
            self->last_disconnect_ms_ = millis();
            // #region agent log
            LOG_W(TAG, String("[DBG5126ae] disconnect event context uptime_ms=") +
                       String(self->last_disconnect_ms_) +
                       " next_reconnect=" + String(self->next_managed_reconnect_ms_) +
                       " write_timeouts=" + String(self->transport_write_timeout_count_) +
                       " tls_timeouts=" + String(self->tls_connect_timeout_count_) +
                       " tcp_errors_other=" + String(self->tcp_transport_error_count_) +
                       " last_errno=" + String(self->last_transport_errno_) +
                       " wifi_connected=" + String(WiFi.isConnected() ? "true" : "false"));
            // #endregion

            // [AUT-745] Classify disconnect cause from counters that are ALREADY
            // reliably populated at this point (no guessing at event->error_handle,
            // which is only guaranteed valid in MQTT_EVENT_ERROR, not here).
            // If none of the local transport-error counters fired before this
            // DISCONNECTED, that is precisely the "Connected-but-Silent" fingerprint:
            // the local stack believed every write succeeded until the broker's
            // keepalive timeout killed the session server-side (AUT-745 DEFECT-2).
            {
                const char* reason_tag = "keepalive_silent";
                if (self->transport_write_timeout_count_ > 0) {
                    reason_tag = "write_timeout";
                } else if (self->tcp_transport_error_count_ > 0) {
                    reason_tag = "tcp_error";
                } else if (self->tls_connect_timeout_count_ > 0) {
                    reason_tag = "tls_timeout";
                } else if (self->last_transport_errno_ != 0) {
                    reason_tag = "errno";
                }
                strncpy(self->last_disconnect_reason_, reason_tag,
                        sizeof(self->last_disconnect_reason_) - 1);
                self->last_disconnect_reason_[sizeof(self->last_disconnect_reason_) - 1] = '\0';
                self->last_disconnect_rssi_ = (int8_t)WiFi.RSSI();
                self->last_disconnect_wifi_connected_ = WiFi.isConnected();
                self->last_disconnect_pending_report_ = true;
                LOG_W(TAG, String("[AUT-745] disconnect classified reason=") + reason_tag +
                           " rssi=" + String(self->last_disconnect_rssi_) +
                           " wifi_connected=" + String(self->last_disconnect_wifi_connected_ ? "true" : "false"));
            }

            // Circuit Breaker: disconnect counts as failure
            self->circuit_breaker_.recordFailure();

            LOG_W(TAG, "MQTT disconnected");
            errorTracker.logCommunicationError(ERROR_MQTT_DISCONNECT, "MQTT connection lost");

            // SAFETY-P4: Start 30s grace timer for offline hysteresis
            // Runs on Core 0 (event task) — offlineModeManager is simple timer state.
            LOG_W(TAG, "[SAFETY-P4] disconnect notified (path=MQTT_EVENT)");
            offlineModeManager.onDisconnect();

            // SAFETY-P1 Mechanism B: Notify Safety-Task (Core 1) to set actuators to safe state.
            // xTaskNotify is ISR-safe and has < 1µs latency.
            // ESP-IDF reconnects automatically — no manual reconnect() needed!
            if (g_safety_task_handle != NULL) {
                xTaskNotify(g_safety_task_handle, NOTIFY_MQTT_DISCONNECTED, eSetBits);
            }

            // Managed reconnect with jitter to reduce reconnect herding when multiple
            // devices drop within the same transport instability window.
            // Avoid duplicate scheduling when MQTT_EVENT_ERROR already queued a reconnect.
            if (!self->manual_reconnect_suspended_ && self->next_managed_reconnect_ms_ == 0) {
                // PKG-18: Boost reconnect delay when write timeouts preceded the disconnect.
                // Breaks the tight reconnect-flap cycle after standby/resume by giving
                // the TCP/TLS stack more time to stabilize before the next attempt.
                unsigned long reconnect_base = MANAGED_RECONNECT_BASE_DELAY_MS;
                if (self->transport_write_timeout_count_ >= WRITE_TIMEOUT_ESCALATION_THRESHOLD) {
                    reconnect_base = MANAGED_RECONNECT_WRITE_TIMEOUT_BOOST_MS;
                    LOG_W(TAG, String("[PKG-18] reconnect delay boosted to ") +
                               String(reconnect_base) + "ms (write_timeouts=" +
                               String(self->transport_write_timeout_count_) + ")");
                }
                // #region agent log
                LOG_W(TAG, String("[DBG5126ae] reconnect base decision write_timeouts=") +
                               String(self->transport_write_timeout_count_) +
                               " threshold=" + String(WRITE_TIMEOUT_ESCALATION_THRESHOLD) +
                               " base_ms=" + String(reconnect_base) +
                               " manual_suspended=" + String(self->manual_reconnect_suspended_ ? 1 : 0));
                // #endregion
                self->scheduleManagedReconnect_("mqtt_disconnected", reconnect_base);
            } else if (self->manual_reconnect_suspended_) {
                LOG_W(TAG, "[INC-EA5484] manual reconnect temporarily suspended");
            } else {
                LOG_D(TAG, "[INC-EA5484] reconnect already scheduled (skip duplicate in DISCONNECTED)");
            }
            break;

        case MQTT_EVENT_DATA: {
            // KRITISCH: event->topic and event->data are NOT null-terminated!
            // All existing handlers (strcmp, strstr, String comparison) expect '\0'.
            // Without null-termination: buffer-overread → crash.
            //
            // INC-2026-04-11-ea5484-mqtt-transport-keepalive:
            // Handle fragmented MQTT_EVENT_DATA frames instead of discarding them.
            // This is required for larger config payloads (e.g. sensors+actuators+offline_rules)
            // where esp-mqtt can deliver chunks across multiple callbacks.
            static char topic_buf[192];
            static char data_buf[8192];
            static size_t expected_len = 0;
            static size_t received_len = 0;
            static bool assembling = false;

            const int total_len_raw = (event->total_data_len > 0) ? event->total_data_len : event->data_len;
            const size_t total_len = static_cast<size_t>(total_len_raw);
            const size_t offset = (event->current_data_offset > 0)
                                      ? static_cast<size_t>(event->current_data_offset)
                                      : 0U;
            const bool starts_new_message = (offset == 0);

            if (starts_new_message) {
                if (total_len >= sizeof(data_buf)) {
                    ESP_LOGE(TAG,
                             "[M2] MQTT_EVENT_DATA too large for reassembly buffer "
                             "(total=%u, capacity=%u) — message dropped",
                             static_cast<unsigned>(total_len),
                             static_cast<unsigned>(sizeof(data_buf) - 1));
                    assembling = false;
                    expected_len = 0;
                    received_len = 0;
                    break;
                }

                // Capture topic only on first chunk.
                size_t tlen = (event->topic_len < static_cast<int>(sizeof(topic_buf) - 1))
                                  ? static_cast<size_t>(event->topic_len)
                                  : sizeof(topic_buf) - 1;
                memcpy(topic_buf, event->topic, tlen);
                topic_buf[tlen] = '\0';
                const bool command_topic = shouldLogAdmissionCorrelation(String(topic_buf));
                static unsigned long s_last_mqtt_data_ingress_dbg_ms = 0;
                const unsigned long ingress_now_ms = millis();
                if (command_topic &&
                    (s_last_mqtt_data_ingress_dbg_ms == 0UL ||
                     (ingress_now_ms - s_last_mqtt_data_ingress_dbg_ms) >= 100UL)) {
                    s_last_mqtt_data_ingress_dbg_ms = ingress_now_ms;
                    // #region agent log
                    LOG_W(TAG, String("[DBG5126ae] mqtt data ingress command ") +
                                   "topic=" + String(topic_buf) +
                                   " total_len=" + String((uint32_t)total_len) +
                                   " chunk_len=" + String((uint32_t)event->data_len) +
                                   " offset=" + String((uint32_t)offset) +
                                   " mqtt_connected=" + String(g_mqtt_connected.load() ? 1 : 0));
                    // #endregion
                }

                expected_len = total_len;
                received_len = 0;
                assembling = true;
            } else if (!assembling) {
                ESP_LOGW(TAG,
                         "[M2] Fragment continuation without active assembly "
                         "(offset=%u, total=%u) — chunk dropped",
                         static_cast<unsigned>(offset),
                         static_cast<unsigned>(total_len));
                break;
            }

            if (!assembling || offset >= sizeof(data_buf)) {
                ESP_LOGW(TAG,
                         "[M2] Invalid fragment bounds (offset=%u, buffer=%u) — message dropped",
                         static_cast<unsigned>(offset),
                         static_cast<unsigned>(sizeof(data_buf)));
                assembling = false;
                expected_len = 0;
                received_len = 0;
                break;
            }

            if (!starts_new_message && offset != received_len) {
                ESP_LOGW(TAG,
                         "[M2] Fragment offset mismatch (expected=%u, got=%u) — resetting assembly",
                         static_cast<unsigned>(received_len),
                         static_cast<unsigned>(offset));
                assembling = false;
                expected_len = 0;
                received_len = 0;
                break;
            }

            const size_t max_copy = expected_len > offset ? (expected_len - offset) : 0U;
            size_t chunk_len = static_cast<size_t>(event->data_len);
            if (chunk_len > max_copy) {
                chunk_len = max_copy;
            }
            if (offset + chunk_len >= sizeof(data_buf)) {
                chunk_len = (sizeof(data_buf) - 1) - offset;
            }

            memcpy(data_buf + offset, event->data, chunk_len);
            received_len = offset + chunk_len;

            if (received_len < expected_len) {
                break;  // Wait for remaining fragments.
            }

            data_buf[expected_len] = '\0';
            const bool command_topic = shouldLogAdmissionCorrelation(String(topic_buf));
            const unsigned long route_started_ms = millis();
            const bool mqtt_connected_before_route = g_mqtt_connected.load();
            g_in_mqtt_event_callback.store(true);
            routeIncomingMessage(topic_buf, data_buf);
            g_in_mqtt_event_callback.store(false);
            const unsigned long route_duration_ms = millis() - route_started_ms;
            if (command_topic || route_duration_ms > 40UL) {
                // #region agent log
                LOG_W(TAG, String("[DBG5126ae] mqtt data route duration ") +
                               "topic=" + String(topic_buf) +
                               " duration_ms=" + String(route_duration_ms) +
                               " payload_len=" + String((uint32_t)expected_len) +
                               " mqtt_before=" + String(mqtt_connected_before_route ? 1 : 0) +
                               " mqtt_after=" + String(g_mqtt_connected.load() ? 1 : 0));
                // #endregion
            }

            assembling = false;
            expected_len = 0;
            received_len = 0;
            break;
        }

        case MQTT_EVENT_SUBSCRIBED: {
            const int mid = event->msg_id;
            LOG_I(TAG, "MQTT_EVENT_SUBSCRIBED msg_id=" + String(mid));
            if (self->bootstrap_heartbeat_pending_) {
                if (!g_mqtt_connected.load()) {
                    LOG_W(TAG, "[SYNC] Ignoring stale SUBSCRIBED bootstrap trigger while disconnected");
                    self->bootstrap_heartbeat_pending_ = false;
                    self->pending_bootstrap_ack_subscribe_msg_id_ = -1;
                    self->pending_bootstrap_config_subscribe_msg_id_ = -1;
                    self->bootstrap_ack_subscription_ready_ = false;
                    self->bootstrap_config_subscription_ready_ = false;
                    self->bootstrap_heartbeat_send_pending_ = false;
                    break;
                }

                if (self->pending_bootstrap_ack_subscribe_msg_id_ >= 0 &&
                    mid == self->pending_bootstrap_ack_subscribe_msg_id_) {
                    self->bootstrap_ack_subscription_ready_ = true;
                    self->pending_bootstrap_ack_subscribe_msg_id_ = -1;
                    LOG_I(TAG, "[SYNC] Bootstrap prerequisite ready: heartbeat ACK subscription active");
                }

                if (self->pending_bootstrap_config_subscribe_msg_id_ >= 0 &&
                    mid == self->pending_bootstrap_config_subscribe_msg_id_) {
                    self->bootstrap_config_subscription_ready_ = true;
                    self->pending_bootstrap_config_subscribe_msg_id_ = -1;
                    LOG_I(TAG, "[SYNC] Bootstrap prerequisite ready: config subscription active");
                }

                if (self->bootstrap_ack_subscription_ready_ && self->bootstrap_config_subscription_ready_) {
                    self->bootstrap_heartbeat_send_pending_ = true;
                    self->bootstrap_heartbeat_pending_ = false;
                    LOG_I(TAG, "[SYNC] Bootstrap heartbeat armed after SUBSCRIBED (ACK+config active)");
                }
            }
            break;
        }

        case MQTT_EVENT_PUBLISHED: {
            // [OUTBOX-1]: IDF OUTBOX slot freed by broker PUBACK. Pairing these
            // against [OUTBOX+1] enqueue logs reveals how fast OUTBOX drains.
            uint32_t ack_cnt = g_puback_count.fetch_add(1) + 1;
            char ack_log[80];
            snprintf(ack_log, sizeof(ack_log),
                     "[OUTBOX-1] PUBACK #%u msg_id=%d heap=%u",
                     (unsigned)ack_cnt, event->msg_id, (unsigned)ESP.getFreeHeap());
            LOG_D(TAG, ack_log);
            if (self->pending_session_announce_msg_id_ >= 0 &&
                event->msg_id == self->pending_session_announce_msg_id_) {
                self->pending_session_announce_msg_id_ = -1;
                resumeAfterAnnounceAck("ack");
            }
            break;
        }

        case MQTT_EVENT_ERROR:
            // INC-2026-04-11-ea5484-mqtt-transport-keepalive (PKG-01):
            // Zusaetzlich errno (z.B. 119/EWOULDBLOCK = Schreib-Timeout) und uptime
            // ausgeben, damit Transport-Schreibtimeout von TLS-Handshake-Timeout im
            // Log eindeutig unterscheidbar ist. Keine Aenderung am LWT-Contract.
            if (event->error_handle != nullptr) {
                ESP_LOGE(TAG, "MQTT_EVENT_ERROR type=%d uptime_ms=%lu",
                         event->error_handle->error_type,
                         (unsigned long)millis());
                if (event->error_handle->error_type == MQTT_ERROR_TYPE_TCP_TRANSPORT) {
                    const int sock_errno = event->error_handle->esp_transport_sock_errno;
                    const int tls_stack = event->error_handle->esp_tls_stack_err;
                    const esp_err_t tls_last = event->error_handle->esp_tls_last_esp_err;

                    const bool write_timeout_explicit = isWritePathTimeoutSignal(sock_errno, tls_stack);
                    const bool tls_timeout = isTlsConnectTimeout(tls_last);
                    // AUT-67: catch IDF-stealth write timeout (all fields neutral
                    // while IDF ESP_LOG already printed errno=119). Only treat as
                    // write timeout when NOT simultaneously a TLS-connect timeout
                    // (preserves correct attribution on TLS reconnect failures).
                    const bool write_timeout_silent =
                        !write_timeout_explicit && !tls_timeout &&
                        isSilentWritePathError(sock_errno, tls_stack, tls_last);
                    const bool write_timeout = write_timeout_explicit || write_timeout_silent;

                    ESP_LOGE(TAG,
                             "  [INC-EA5484] TCP transport error sock_errno=%d (%s) "
                             "tls_stack=%d esp_tls_last=%s classified=%s",
                             sock_errno,
                             strerror(sock_errno),
                             tls_stack,
                             esp_err_to_name(tls_last),
                             write_timeout_silent ? "write_timeout_silent"
                                                  : write_timeout_explicit ? "write_timeout"
                                                  : tls_timeout ? "tls_timeout"
                                                  : "tcp_other");
                    // #region agent log
                    LOG_W(TAG, String("[DBG5126ae] transport error context type=tcp_transport") +
                                   " sock_errno=" + String(sock_errno) +
                                   " tls_stack=" + String(tls_stack) +
                                   " tls_last=" + String(esp_err_to_name(tls_last)) +
                                   " write_timeout_explicit=" + String(write_timeout_explicit ? 1 : 0) +
                                   " write_timeout_silent=" + String(write_timeout_silent ? 1 : 0) +
                                   " tls_timeout=" + String(tls_timeout ? 1 : 0) +
                                   " last_errno_before=" + String(self->last_transport_errno_) +
                                   " next_reconnect_before=" + String(self->next_managed_reconnect_ms_) +
                                   " qos1_enqueued=" + String(g_qos1_enqueue_count.load()) +
                                   " puback_count=" + String(g_puback_count.load()) +
                                   " outbox_full_count=" + String(g_publish_outbox_full_count.load()) +
                                   " outbox_inflight=" + String(
                                       g_qos1_enqueue_count.load() >= g_puback_count.load()
                                           ? (g_qos1_enqueue_count.load() - g_puback_count.load())
                                           : 0U) +
                                   " ack_age_ms=" + String(
                                       g_last_server_ack_ms.load() > 0
                                           ? (millis() - g_last_server_ack_ms.load())
                                           : 0UL));
                    // #endregion

                    // Preserve meaningful marker for SafePublish retry/backpressure
                    // heuristic: 119 = IDF write-path timeout (EWOULDBLOCK-ish).
                    // Real sock_errno wins if present; otherwise surface the silent
                    // timeout as 119 so `isWritePathTimeoutErrno(last_transport_errno_)`
                    // downstream (mqtt_client.cpp:1110) classifies correctly.
                    if (sock_errno != 0) {
                        self->last_transport_errno_ = sock_errno;
                    } else if (write_timeout_silent) {
                        self->last_transport_errno_ = 119;
                    } else {
                        self->last_transport_errno_ = 0;
                    }

                    if (write_timeout) {
                        self->transport_write_timeout_count_++;
                    }
                    if (tls_timeout) {
                        self->tls_connect_timeout_count_++;
                    }
                    if (!write_timeout && !tls_timeout) {
                        self->tcp_transport_error_count_++;
                    }

                    // Let MQTT_EVENT_DISCONNECTED own reconnect scheduling.
                    // Runtime evidence (H7/H11/H14) shows tls_timeout-triggered scheduling
                    // from MQTT_EVENT_ERROR can amplify reconnect churn with duplicate plans.
                    if (tls_timeout) {
                        // #region agent log
                        LOG_W(TAG, String("[DBG5126ae] tls timeout defer reconnect to disconnected next_before=") +
                                       String(self->next_managed_reconnect_ms_) +
                                       " last_disconnect=" + String(self->last_disconnect_ms_));
                        // #endregion
                    }
                } else if (event->error_handle->error_type == MQTT_ERROR_TYPE_CONNECTION_REFUSED) {
                    ESP_LOGE(TAG, "  Connection refused, reason=%d",
                             event->error_handle->connect_return_code);
                }
            }
            break;

        default:
            break;
    }
}
#endif  // !MQTT_USE_PUBSUBCLIENT

// ============================================
// PUBSUBCLIENT-SPECIFIC IMPLEMENTATIONS
// (only compiled when MQTT_USE_PUBSUBCLIENT is defined)
// ============================================
#ifdef MQTT_USE_PUBSUBCLIENT

bool MQTTClient::connectToBroker() {
    LOG_I(TAG, "Connecting to MQTT broker: " + current_config_.server + ":" + String(current_config_.port));

    // Build Last-Will
    String last_will_topic = String(TopicBuilder::buildSystemHeartbeatTopic());
    last_will_topic.replace("/heartbeat", "/will");

    time_t will_timestamp = timeManager.getUnixTimestamp();
    String last_will_message = "{\"status\":\"offline\",\"esp_id\":\"" + g_system_config.esp_id +
                               "\",\"reason\":\"unexpected_disconnect\",\"timestamp\":" +
                               String((unsigned long)will_timestamp) + "}";

    LOG_I(TAG, "Last-Will Topic: " + last_will_topic);

    const String original_host = current_config_.server;
    const uint16_t original_port = current_config_.port;
    String host_candidates[5] = {original_host, "", "", "", ""};
    uint8_t host_candidate_count = 1;

    #ifdef WOKWI_SIMULATION
    if (original_host == "host.wokwi.internal") {
        host_candidates[host_candidate_count++] = "host.docker.internal";
        host_candidates[host_candidate_count++] = "10.13.37.1";
        host_candidates[host_candidate_count++] = "192.168.0.39";
        host_candidates[host_candidate_count++] = "127.0.0.1";
    }
    #endif

    bool connected = false;
    for (uint8_t idx = 0; idx < host_candidate_count && !connected; idx++) {
        current_config_.server = host_candidates[idx];
        current_config_.port = original_port;
        mqtt_.setServer(current_config_.server.c_str(), current_config_.port);

        if (idx > 0) {
            LOG_W(TAG, "MQTT host fallback active: trying " + current_config_.server);
        }

        // ✅ FIX #2: Auto-Fallback von Port 8883 → 1883
        connected = attemptMQTTConnection(last_will_topic, last_will_message);

        if (!connected && current_config_.port == 8883) {
            LOG_W(TAG, "Port 8883 (TLS) failed - trying port 1883 (plain MQTT)");
            current_config_.port = 1883;
            mqtt_.setServer(current_config_.server.c_str(), current_config_.port);
            connected = attemptMQTTConnection(last_will_topic, last_will_message);
            if (connected) {
                LOG_I(TAG, "✅ Port-Fallback successful! Connected on port 1883");
            }
        }
    }

    if (connected) {
        if (current_config_.server != original_host) {
            LOG_I(TAG, "MQTT connected via host fallback: " + current_config_.server);
        }
        LOG_I(TAG, "MQTT connected!");
        reconnect_attempts_ = 0;
        reconnect_delay_ms_ = RECONNECT_BASE_DELAY_MS;
        circuit_breaker_.recordSuccess();
        registration_confirmed_ = false;
        registration_start_ms_ = millis();
        registration_timeout_logged_ = false;
#ifdef ENABLE_METRICS_SPLIT
        metrics_skip_count_ = METRICS_MAX_SKIP_COUNT;
#endif
        LOG_I(TAG, "Registration gate closed - awaiting heartbeat ACK");
        processOfflineBuffer();
        if (on_connect_callback_) {
            on_connect_callback_();
        }
        return true;
    } else {
        current_config_.server = original_host;
        current_config_.port = original_port;
        LOG_E(TAG, "MQTT connection failed, rc=" + String(mqtt_.state()));
        errorTracker.logCommunicationError(ERROR_MQTT_CONNECT_FAILED,
                                           ("MQTT connection failed, rc=" + String(mqtt_.state())).c_str());
        return false;
    }
}

bool MQTTClient::attemptMQTTConnection(const String& last_will_topic, const String& last_will_message) {
    bool result = false;
    if (anonymous_mode_) {
        result = mqtt_.connect(
            current_config_.client_id.c_str(),
            last_will_topic.c_str(),
            1,     // QoS 1
            true,  // Retain
            last_will_message.c_str()
        );
    } else {
        result = mqtt_.connect(
            current_config_.client_id.c_str(),
            current_config_.username.c_str(),
            current_config_.password.c_str(),
            last_will_topic.c_str(),
            1,     // QoS 1
            true,  // Retain
            last_will_message.c_str()
        );
    }
    return result;
}

void MQTTClient::handleDisconnection() {
    static bool disconnection_logged = false;

    registration_confirmed_ = false;
    registration_start_ms_ = 0;
    registration_timeout_logged_ = false;
    LOG_D(TAG, "Registration gate closed due to disconnect");

    if (actuatorManager.isInitialized()) {
        if (offlineModeManager.getOfflineRuleCount() > 0) {
            LOG_W(TAG, "[SAFETY] MQTT disconnected — " +
                  String(offlineModeManager.getOfflineRuleCount()) +
                  " offline rules available, delegating to P4");
        } else {
            actuatorManager.setAllActuatorsToSafeState();
            LOG_W(TAG, "[SAFETY] MQTT disconnected — no offline rules, safe state immediately");
        }
    }

    // SAFETY-P4: Start 30s grace timer for offline hysteresis
    LOG_W(TAG, "[SAFETY-P4] disconnect notified (path=PubSubClient)");
    offlineModeManager.onDisconnect();

    if (!disconnection_logged) {
        LOG_W(TAG, "MQTT disconnected");
        errorTracker.logCommunicationError(ERROR_MQTT_DISCONNECT, "MQTT connection lost");
        disconnection_logged = true;
    }

    reconnect();

    if (isConnected()) {
        disconnection_logged = false;
    }
}

bool MQTTClient::shouldAttemptReconnect() const {
    if (circuit_breaker_.getState() == CircuitState::HALF_OPEN) {
        return true;
    }
    unsigned long current_time = millis();
    if (current_time - last_reconnect_attempt_ < reconnect_delay_ms_) {
        return false;
    }
    return true;
}

void MQTTClient::processOfflineBuffer() {
    if (offline_buffer_count_ == 0) return;

    LOG_I(TAG, "Processing offline buffer (" + String(offline_buffer_count_) + " messages)");

    uint16_t processed = 0;
    for (uint16_t i = 0; i < offline_buffer_count_; i++) {
        if (publish(offline_buffer_[i].topic, offline_buffer_[i].payload, offline_buffer_[i].qos)) {
            processed++;
        } else {
            break;
        }
    }

    if (processed > 0) {
        uint16_t remaining = offline_buffer_count_ - processed;
        for (uint16_t i = 0; i < remaining; i++) {
            offline_buffer_[i] = offline_buffer_[i + processed];
        }
        offline_buffer_count_ = remaining;
        LOG_I(TAG, "Processed " + String(processed) + " offline messages, " +
                   String(remaining) + " remaining");
    }

    // AUT-714: Flush LittleFS spool (persistent across reboots)
    if (spoolManager.isEnabled() && spoolManager.pendingCount() > 0) {
        ESP_LOGI("MQTT", "Flushing spool: %lu entries", (unsigned long)spoolManager.pendingCount());
        spoolManager.flushPending(*this);
    }
}

bool MQTTClient::addToOfflineBuffer(const String& topic, const String& payload, uint8_t qos) {
    if (payload.length() == 0) {
        LOG_W(TAG, "Empty payload rejected from offline buffer: " + topic);
        return false;
    }
    if (offline_buffer_count_ >= MAX_OFFLINE_MESSAGES) {
        LOG_E(TAG, "Offline buffer full, dropping message");
        errorTracker.logCommunicationError(ERROR_MQTT_BUFFER_FULL, "Offline buffer full");
        return false;
    }
    offline_buffer_[offline_buffer_count_].topic     = topic;
    offline_buffer_[offline_buffer_count_].payload   = payload;
    offline_buffer_[offline_buffer_count_].qos       = qos;
    offline_buffer_[offline_buffer_count_].timestamp = millis();
    offline_buffer_count_++;
    LOG_D(TAG, "Added to offline buffer (count: " + String(offline_buffer_count_) + ")");
    return true;
}

unsigned long MQTTClient::calculateBackoffDelay() const {
    unsigned long delay = RECONNECT_BASE_DELAY_MS * (1 << reconnect_attempts_);
    if (delay > RECONNECT_MAX_DELAY_MS) {
        delay = RECONNECT_MAX_DELAY_MS;
    }
    return delay;
}

void MQTTClient::staticCallback(char* topic, byte* payload, unsigned int length) {
    if (!instance_) return;

    String topic_str = String(topic);
    String payload_str;
    payload_str.reserve(length);
    for (unsigned int i = 0; i < length; i++) {
        payload_str += (char)payload[i];
    }

    if (instance_->message_callback_) {
        instance_->message_callback_(topic_str, payload_str);
    }
}

#endif  // MQTT_USE_PUBSUBCLIENT
