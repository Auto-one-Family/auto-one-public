#ifndef SERVICES_COMMUNICATION_MQTT_CLIENT_H
#define SERVICES_COMMUNICATION_MQTT_CLIENT_H

// ============================================
// MQTT BACKEND SELECTION (SAFETY-RTOS M5.1)
// ============================================
// Default (no flag)        → ESP-IDF esp_mqtt_client (non-blocking, eigener FreeRTOS-Task)
// MQTT_USE_PUBSUBCLIENT=1  → PubSubClient (Arduino, blocking reconnect — seeed/wokwi only)
// ============================================
#ifndef MQTT_USE_PUBSUBCLIENT
    // ACHTUNG Namenskonflikt: Dieses File heisst mqtt_client.h.
    // Der Arduino-ESP32-SDK liefert die ESP-IDF-MQTT-API als mqtt_client.h (kein esp_mqtt_client.h).
    // Korrekt: <mqtt_client.h> mit angle brackets.
    //   PlatformIO haengt -I.../tools/sdk/esp32/include/mqtt/esp-mqtt/include ein.
    //   Winkel-Brackets (<>) suchen dort DIREKT nach mqtt_client.h — findet SDK-Header.
    //   Unser Header liegt in src/services/communication/ und ist NICHT via -Isrc direkt sichtbar.
    //   Daher kein Konflikt solange unser Header nie in src/ (flach) liegt.
    // FALSCH: "mqtt_client.h" — bindet immer dieses File ein (relative Suche zuerst).
    // FALSCH: <mqtt/esp-mqtt/include/mqtt_client.h> — sdk root ist kein -I-Pfad.
    #include <mqtt_client.h>
    #include <freertos/FreeRTOS.h>
    #include <freertos/task.h>
    #include <atomic>
#else
    #include <PubSubClient.h>
    #include <WiFiClient.h>
#endif

#include <Arduino.h>
#include <functional>
#include "../../utils/logger.h"
#include "../../utils/topic_builder.h"
#include "../../error_handling/error_tracker.h"
#include "../../error_handling/circuit_breaker.h"
#include "../../models/system_types.h"
#include "../../config/feature_flags.h"

// ============================================
// MQTT CONFIGURATION STRUCTURE
// ============================================
struct MQTTConfig {
    String server;
    uint16_t port;
    String client_id;
    String username;        // Optional - can be empty (Anonymous Mode)
    String password;        // Optional - can be empty (Anonymous Mode)
    int keepalive;
    int timeout;
};

enum class PublishFailureReasonClass : uint8_t {
    None = 0,
    CircuitBreakerOpen = 1,
    QueueShed = 2,
    OutboxFull = 3,
    TransportError = 4,
};

// ============================================
// MQTT MESSAGE (offline buffer — PubSubClient path only)
// ============================================
#ifdef MQTT_USE_PUBSUBCLIENT
struct MQTTMessage {
    String topic;
    String payload;
    uint8_t qos;
    unsigned long timestamp;
};
#endif

// ============================================
// SHARED STATE: MQTT connection flag + last server ACK timestamp
// Written by MQTT_EVENT_CONNECTED/DISCONNECTED (Core 0).
// Read by Safety-Task checkServerAckTimeout() (Core 1).
// ============================================
#ifndef MQTT_USE_PUBSUBCLIENT
extern std::atomic<bool>     g_mqtt_connected;
// SAFETY-P1 Race-Fix: reset atomically in MQTT_EVENT_CONNECTED (Core 0) before
// on_connect_callback_ fires, so Safety-Task (Core 1) never sees the stale
// pre-reconnect timestamp with mqttClient.isConnected()==true.
extern std::atomic<uint32_t> g_last_server_ack_ms;
#endif

// ============================================
// MQTT CLIENT CLASS (Phase 2 - Communication Layer)
// ============================================
class MQTTClient {
public:
    // Singleton Pattern
    static MQTTClient& getInstance();

    // Initialization
    bool begin();

    // Connection Management
    bool connect(const MQTTConfig& config);
    bool disconnect();
    bool isConnected();
    void reconnect();  // no-op in ESP-IDF path (automatic reconnect)

    // Authentication Transition (Anonymous → Authenticated)
    bool transitionToAuthenticated(const String& username, const String& password);
    bool isAnonymousMode() const;

    // Publishing
    bool publish(const String& topic, const String& payload, uint8_t qos = 1);
    PublishFailureReasonClass getLastPublishFailureReasonClass() const;
    const char* getLastPublishFailureReasonClassName() const;
    bool safePublish(const String& topic, const String& payload, uint8_t qos = 1, uint8_t retries = 3);
    void setTestPublishHook(std::function<void(const String&, const String&)> hook);
    void clearTestPublishHook();

    // Subscription (qos: 0=at most once, 1=at least once)
    bool subscribe(const String& topic, uint8_t qos = 0);
    // Queue-based subscribe for staged post-connect recovery (ESP-IDF).
    bool queueSubscribe(const String& topic, uint8_t qos = 0, bool critical = false);
    bool unsubscribe(const String& topic);
    // Trigger one fast registration heartbeat once heartbeat/ack subscription is active.
    void requestBootstrapHeartbeatAfterAck();
    void setCallback(std::function<void(const String&, const String&)> callback);
    // SAFETY-P1 Mechanism A: Callback fired after every successful MQTT connect (initial + reconnect)
    void setOnConnectCallback(std::function<void()> callback);

    // Heartbeat
    void publishHeartbeat(bool force = false);

    // Status
    String getConnectionStatus();
    uint16_t getConnectionAttempts() const;
    bool hasOfflineMessages() const;
    uint16_t getOfflineMessageCount() const;

    // Monitoring — In ESP-IDF path: handles timeManager + heartbeat only (no reconnect logic)
    void loop();

#ifndef MQTT_USE_PUBSUBCLIENT
    // M3: Drain publish queue — called from Communication-Task (Core 0).
    // Safety-Task (Core 1) enqueues via queuePublish(); Core 0 drains here.
    void processPublishQueue();
    // Drain deferred subscribe queue (one topic per tick with backoff).
    void processSubscriptionQueue();
    // Send deferred bootstrap heartbeat outside MQTT event callback context.
    void processBootstrapHeartbeatAfterSubscribe();
#endif

    // Circuit Breaker Access (for Watchdog integration + persistent failure timer)
    CircuitState getCircuitBreakerState() const;
    uint8_t getCircuitBreakerFailureCount() const;

    // Sequence number for cross-layer correlation
    uint32_t getNextSeq();
    uint32_t getCurrentSeq() const;

    // Boot segment id (ESP reset reason + boot_count) for correlating lifecycle events
    String getBootTelemetrySequenceId() const;

    // ESP-IDF MQTT client outbox full (-2) drops for non-critical publishes (telemetry only)
    uint32_t getPublishOutboxNoncriticalDropCount() const;

    // [FIX5-VERIFY] Total MQTT outbox-full events (msg_id == -2), all topic classes.
    // Distinct from NoncriticalDropCount: critical topics go to NVS replay, still counted here.
    uint32_t getPublishOutboxFullCount() const;

    // AUT-57: safePublish retry telemetry (total retries across all calls)
    uint32_t getSafePublishRetryCount() const;

    // ============================================
    // REGISTRATION GATE (Bug #1 Fix)
    // ============================================
    bool isRegistrationConfirmed() const;
    void confirmRegistration();
    // Registration timeout observer (independent of publish() calls).
    // IMPORTANT: Fail-closed behavior — timeout never opens the gate without valid ACK.
    bool checkRegistrationTimeout();

private:
    MQTTClient();
    ~MQTTClient();

    // Prevent copy
    MQTTClient(const MQTTClient&) = delete;
    MQTTClient& operator=(const MQTTClient&) = delete;

    // ============================================
    // BACKEND-SPECIFIC MEMBERS
    // ============================================
#ifndef MQTT_USE_PUBSUBCLIENT
    struct PendingSubscription {
        String topic;
        uint8_t qos;
        uint8_t attempts;
        bool critical;
        unsigned long next_attempt_ms;
    };

    static const uint8_t MAX_PENDING_SUBSCRIPTIONS = 16;
    static const uint8_t MAX_SUBSCRIBE_RETRIES = 6;
    static const unsigned long SUBSCRIBE_RETRY_BASE_MS = 200;
    static const unsigned long SUBSCRIBE_RETRY_MAX_MS = 5000;
    // AUT-484 F1: Pace post-connect SUBSCRIBE bursts (keepalive/TCP headroom).
    static const unsigned long SUBSCRIPTION_INTER_PACE_MS = 120;
    // AUT-484: Pace runtime actuator/response + intent_outcome publishes (post-connect).
    static const unsigned long RUNTIME_CRITICAL_PUBLISH_INTER_PACE_MS = 120;

    // ESP-IDF MQTT client handle
    esp_mqtt_client_handle_t mqtt_client_;

    // Static event handler (runs in ESP-IDF MQTT Task, Core 0)
    // args = MQTTClient* instance (passed during event registration)
    static void mqtt_event_handler(void* args, esp_event_base_t base,
                                   int32_t event_id, void* event_data);

    bool enqueueSubscription_(const String& topic, uint8_t qos, bool critical, bool front = false);
    void clearSubscriptionQueue_();
    bool shouldApplyRuntimeCriticalPublishPace_(const String& topic) const;
    bool deferRuntimeCriticalPublishPace_(const String& topic,
                                          const String& payload,
                                          uint8_t qos,
                                          bool critical,
                                          PublishFailureReasonClass* set_reason);
    void markRuntimeCriticalPublishCompleted_(const String& topic);
    void scheduleManagedReconnect_(const char* reason, unsigned long base_delay_ms = 1500);
    void processManagedReconnect_();
    unsigned long computeReconnectJitterMs_(uint16_t attempt) const;
    bool publishSessionAnnounce(uint32_t epoch);
#else
    // PubSubClient backend
    WiFiClient wifi_client_;
    PubSubClient mqtt_;

    // Offline buffer — reduced from 100 to 25 (saves 2400 bytes BSS + prevents
    // 60KB heap spike when full with large String payloads) (MEM-OPT-3)
    static const uint16_t MAX_OFFLINE_MESSAGES = 25;
    MQTTMessage offline_buffer_[MAX_OFFLINE_MESSAGES];
    uint16_t offline_buffer_count_;

    // Reconnect management (PubSubClient: manual; ESP-IDF: automatic)
    unsigned long last_reconnect_attempt_;
    uint16_t reconnect_attempts_;
    unsigned long reconnect_delay_ms_;

    // PubSubClient-specific helpers
    bool connectToBroker();
    bool attemptMQTTConnection(const String& last_will_topic, const String& last_will_message);
    void handleDisconnection();
    bool shouldAttemptReconnect() const;
    void processOfflineBuffer();
    bool addToOfflineBuffer(const String& topic, const String& payload, uint8_t qos);
    unsigned long calculateBackoffDelay() const;

    // Static callback for PubSubClient
    static void staticCallback(char* topic, byte* payload, unsigned int length);
#endif

    // ============================================
    // COMMON MEMBERS (both paths)
    // ============================================
    MQTTConfig current_config_;

    bool initialized_;
    bool anonymous_mode_;

    // Heartbeat
    unsigned long last_heartbeat_;
    static const unsigned long HEARTBEAT_INTERVAL_MS = 60000;  // 60 seconds (normal operation)
    // While registration gate is closed, retry heartbeat faster to avoid long stalls
    // when the first post-connect heartbeat or ACK is lost.
    static const unsigned long HEARTBEAT_REGISTRATION_RETRY_MS = 5000;  // 5 seconds

    // Callbacks
    std::function<void(const String&, const String&)> message_callback_;
    std::function<void()> on_connect_callback_;  // SAFETY-P1: fired after every successful connect

    // Circuit Breaker (Phase 6+)
    CircuitBreaker circuit_breaker_;

    // Sequence number for correlation (monotonically increasing per publish)
    uint32_t publish_seq_;

    // AUT-57: cumulative retry count across all safePublish calls (telemetry only)
    uint32_t safe_publish_retry_count_;
    PublishFailureReasonClass last_publish_failure_reason_;

    // ============================================
    // AUT-121: HEARTBEAT METRICS SPLIT
    // ============================================
#ifdef ENABLE_METRICS_SPLIT
    struct MetricsSnapshot {
        uint32_t publish_outbox_full_count;  // [FIX5-VERIFY] total msg_id==-2 events
        uint32_t offline_enter_count;
        uint32_t adopting_enter_count;
        uint32_t adoption_noop_count;
        uint32_t adoption_delta_count;
        uint32_t handover_abort_count;
        uint32_t handover_contract_reject_count;
        uint32_t persistence_drift_count;
        uint32_t critical_outcome_drop_count;
        uint32_t publish_outbox_drop_count;
        uint32_t sensor_cmd_queue_overflow_count;
        uint32_t safe_publish_retry_count;
        uint32_t intent_chain_stage_enqueue_fail_count;
        uint32_t emergency_rejected_no_token_total;
    };
    MetricsSnapshot last_metrics_;
    uint8_t metrics_skip_count_;
    static const uint8_t METRICS_MAX_SKIP_COUNT = 5;
    void publishHeartbeatMetrics();
    bool metricsChanged_(const MetricsSnapshot& current) const;
#endif

    // ============================================
    // REGISTRATION GATE (Bug #1 Fix)
    // ============================================
    bool registration_confirmed_;
    unsigned long registration_start_ms_;
    bool registration_timeout_logged_;
    static const unsigned long REGISTRATION_TIMEOUT_MS = 10000;

#ifndef MQTT_USE_PUBSUBCLIENT
    PendingSubscription pending_subscriptions_[MAX_PENDING_SUBSCRIPTIONS];
    uint8_t pending_subscription_count_;
    bool bootstrap_heartbeat_pending_;
    /** msg_id from esp_mqtt_client_subscribe(heartbeat/ack); bootstrap HB after MQTT_EVENT_SUBSCRIBED */
    int pending_bootstrap_ack_subscribe_msg_id_;
    /** msg_id from esp_mqtt_client_subscribe(config); bootstrap HB waits until config lane is active */
    int pending_bootstrap_config_subscribe_msg_id_;
    /** Tracks SUBSCRIBED events for bootstrap prerequisites (reset on connect/disconnect). */
    bool bootstrap_ack_subscription_ready_;
    bool bootstrap_config_subscription_ready_;
    bool bootstrap_heartbeat_send_pending_;
    unsigned long next_managed_reconnect_ms_;
    uint16_t managed_reconnect_attempts_;
    bool is_connecting_;          // AUT-656-A: true while TLS handshake in-flight after reconnect() ESP_OK
    unsigned long is_connecting_since_ms_;  // AUT-676: watchdog timestamp; set when is_connecting_ becomes true
    uint32_t transport_write_timeout_count_;
    uint32_t tls_connect_timeout_count_;
    uint32_t tcp_transport_error_count_;
    int32_t last_transport_errno_;
    unsigned long last_disconnect_ms_;
    bool manual_reconnect_suspended_;
    int pending_session_announce_msg_id_;
    unsigned long last_runtime_critical_publish_ms_;

    // [AUT-745] Last-disconnect diagnostics — captured in MQTT_EVENT_DISCONNECTED,
    // surfaced once via the next successful heartbeat's runtime_telemetry so the
    // "Connected-but-Silent" defect (silence after CONNACK, broker-side keepalive
    // kill) is visible server-side even without physical Serial access.
    char last_disconnect_reason_[20];
    int8_t last_disconnect_rssi_;
    bool last_disconnect_wifi_connected_;
    bool last_disconnect_pending_report_;
#endif

    static MQTTClient* instance_;
    static std::function<void(const String&, const String&)> test_publish_hook_;
};

// ============================================
// GLOBAL MQTT CLIENT INSTANCE
// ============================================
extern MQTTClient& mqttClient;

#endif // SERVICES_COMMUNICATION_MQTT_CLIENT_H
