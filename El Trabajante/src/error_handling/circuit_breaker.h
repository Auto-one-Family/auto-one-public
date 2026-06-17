#ifndef ERROR_HANDLING_CIRCUIT_BREAKER_H
#define ERROR_HANDLING_CIRCUIT_BREAKER_H

#include <Arduino.h>

// ============================================
// CIRCUIT BREAKER STATES
// ============================================
enum class CircuitState : uint8_t {
  CLOSED = 0,      // Normal operation, requests allowed
  OPEN,            // Service failed, requests blocked
  HALF_OPEN        // Testing recovery, limited requests allowed
};

// ============================================
// CIRCUIT BREAKER CLASS (Phase 6+)
// ============================================
/**
 * @brief Circuit Breaker Pattern für Service-Protection
 * 
 * Verhindert Retry-Spam bei Service-Ausfällen (MQTT, WiFi, etc.)
 * 
 * State Machine:
 * - CLOSED: Normal operation, alle Requests erlaubt
 * - OPEN: Nach X Fehlern → blockiert alle Requests für Recovery-Timeout
 * - HALF_OPEN: Nach Recovery-Timeout → erlaubt Test-Request
 *   - Success → zurück zu CLOSED
 *   - Failure → zurück zu OPEN
 * 
 * @example
 * ```cpp
 * CircuitBreaker mqtt_breaker("MQTT", 5, 30000, 10000);
 * 
 * if (mqtt_breaker.allowRequest()) {
 *   bool success = mqtt_client.publish(topic, payload);
 *   if (success) {
 *     mqtt_breaker.recordSuccess();
 *   } else {
 *     mqtt_breaker.recordFailure();
 *   }
 * }
 * ```
 */
class CircuitBreaker {
public:
  /**
   * @brief Constructor
   * @param service_name Name des Services (für Logging)
   * @param failure_threshold Anzahl Fehler bis OPEN (z.B. 5)
   * @param recovery_timeout_ms Zeit in OPEN vor HALF_OPEN Test (z.B. 30000 = 30s)
   * @param halfopen_timeout_ms Maximale Zeit in HALF_OPEN (z.B. 10000 = 10s)
   */
  CircuitBreaker(const char* service_name, 
                 uint8_t failure_threshold = 5, 
                 unsigned long recovery_timeout_ms = 30000,
                 unsigned long halfopen_timeout_ms = 10000);
  
  // ============================================
  // PUBLIC API
  // ============================================
  
  /**
   * @brief Check ob Request erlaubt ist
   * @return true wenn Request erlaubt (CLOSED oder HALF_OPEN Test)
   * @return false wenn Request blockiert (OPEN)
   */
  bool allowRequest();
  
  /**
   * @brief Record Success (Reset Failure Counter)
   * @note Call nach jedem erfolgreichen Request
   * @note HALF_OPEN → CLOSED Transition
   */
  void recordSuccess();
  
  /**
   * @brief Record Failure (Increment Failure Counter)
   * @note Call nach jedem fehlgeschlagenen Request
   * @note CLOSED → OPEN bei Threshold erreicht
   * @note HALF_OPEN → OPEN bei Test-Failure
   */
  void recordFailure();
  
  /**
   * @brief Reset Circuit Breaker zu CLOSED (manuell)
   * @note Useful für Admin-Commands oder Recovery-Override
   */
  void reset();
  
  // ============================================
  // STATUS QUERIES
  // ============================================
  
  /**
   * @brief Check ob Circuit Breaker OPEN ist
   * @return true wenn OPEN (Service blockiert)
   */
  bool isOpen() const;
  
  /**
   * @brief Check ob Circuit Breaker CLOSED ist
   * @return true wenn CLOSED (Normal Operation)
   */
  bool isClosed() const;
  
  /**
   * @brief Get Current State
   * @return CircuitState (CLOSED, OPEN, HALF_OPEN)
   */
  CircuitState getState() const;
  
  /**
   * @brief Get Failure Count
   * @return uint8_t Current failure count
   */
  uint8_t getFailureCount() const;
  
  /**
   * @brief Get Service Name
   * @return const char* Service name
   */
  const char* getServiceName() const;
  
private:
  // Service identification
  const char* service_name_;
  
  // Configuration
  uint8_t failure_threshold_;
  unsigned long recovery_timeout_ms_;
  unsigned long halfopen_timeout_ms_;
  
  // State
  CircuitState state_;
  uint8_t failure_count_;
  unsigned long last_failure_time_;
  unsigned long state_change_time_;
  
  // Helper methods
  void transitionTo(CircuitState new_state);
  bool shouldAttemptRecovery() const;
  bool halfOpenTestTimedOut() const;
};

#endif // ERROR_HANDLING_CIRCUIT_BREAKER_H

