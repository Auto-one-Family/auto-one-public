#include "circuit_breaker.h"
#include "../utils/logger.h"

// ESP-IDF TAG convention for structured logging
static const char* TAG = "CBREAKER";

// ============================================
// CONSTRUCTOR
// ============================================
CircuitBreaker::CircuitBreaker(const char* service_name, 
                               uint8_t failure_threshold, 
                               unsigned long recovery_timeout_ms,
                               unsigned long halfopen_timeout_ms)
  : service_name_(service_name),
    failure_threshold_(failure_threshold),
    recovery_timeout_ms_(recovery_timeout_ms),
    halfopen_timeout_ms_(halfopen_timeout_ms),
    state_(CircuitState::CLOSED),
    failure_count_(0),
    last_failure_time_(0),
    state_change_time_(millis())
{
  LOG_I(TAG, "CircuitBreaker created for service: " + String(service_name_));
  LOG_D(TAG, "  Failure Threshold: " + String(failure_threshold_));
  LOG_D(TAG, "  Recovery Timeout: " + String(recovery_timeout_ms_) + " ms");
  LOG_D(TAG, "  Half-Open Timeout: " + String(halfopen_timeout_ms_) + " ms");
}

// ============================================
// ALLOW REQUEST - Main Entry Point
// ============================================
bool CircuitBreaker::allowRequest() {
  // ============================================
  // STATE: CLOSED (Normal Operation)
  // ============================================
  if (state_ == CircuitState::CLOSED) {
    // All requests allowed
    return true;
  }
  
  // ============================================
  // STATE: OPEN (Service Failed)
  // ============================================
  if (state_ == CircuitState::OPEN) {
    // Check if recovery timeout elapsed
    if (shouldAttemptRecovery()) {
      LOG_I(TAG, "CircuitBreaker [" + String(service_name_) + "]: Attempting recovery → HALF_OPEN");
      transitionTo(CircuitState::HALF_OPEN);
      return true;  // Allow ONE test request
    }
    
    // Still in OPEN state, block request
    return false;
  }
  
  // ============================================
  // STATE: HALF_OPEN (Testing Recovery)
  // ============================================
  if (state_ == CircuitState::HALF_OPEN) {
    // Check if test timed out
    if (halfOpenTestTimedOut()) {
      LOG_W(TAG, "CircuitBreaker [" + String(service_name_) + "]: HALF_OPEN test timed out → OPEN");
      transitionTo(CircuitState::OPEN);
      return false;
    }
    
    // Allow test request (caller must call recordSuccess/recordFailure)
    return true;
  }
  
  // Fallback (should never reach)
  return false;
}

// ============================================
// RECORD SUCCESS
// ============================================
void CircuitBreaker::recordSuccess() {
  if (state_ == CircuitState::HALF_OPEN) {
    // HALF_OPEN → CLOSED (Recovery successful)
    LOG_I(TAG, "CircuitBreaker [" + String(service_name_) + "]: Recovery successful → CLOSED");
    failure_count_ = 0;
    transitionTo(CircuitState::CLOSED);
    
  } else if (state_ == CircuitState::CLOSED) {
    // Reset failure count on any success in CLOSED state
    if (failure_count_ > 0) {
      LOG_D(TAG, "CircuitBreaker [" + String(service_name_) + "]: Failure count reset (was: " + String(failure_count_) + ")");
      failure_count_ = 0;
    }
  }
}

// ============================================
// RECORD FAILURE
// ============================================
void CircuitBreaker::recordFailure() {
  last_failure_time_ = millis();
  failure_count_++;
  
  LOG_W(TAG, "CircuitBreaker [" + String(service_name_) + "]: Failure recorded (count: " + String(failure_count_) + "/" + String(failure_threshold_) + ")");
  
  // ============================================
  // STATE: CLOSED → Check Threshold
  // ============================================
  if (state_ == CircuitState::CLOSED) {
    if (failure_count_ >= failure_threshold_) {
      LOG_E(TAG, "CircuitBreaker [" + String(service_name_) + "]: Failure threshold reached → OPEN");
      LOG_E(TAG, "  Service will be unavailable for " + String(recovery_timeout_ms_ / 1000) + " seconds");
      transitionTo(CircuitState::OPEN);
    }
  }
  
  // ============================================
  // STATE: HALF_OPEN → Back to OPEN
  // ============================================
  else if (state_ == CircuitState::HALF_OPEN) {
    LOG_W(TAG, "CircuitBreaker [" + String(service_name_) + "]: Recovery test failed → OPEN");
    transitionTo(CircuitState::OPEN);
  }
}

// ============================================
// RESET (Manual Override)
// ============================================
void CircuitBreaker::reset() {
  LOG_I(TAG, "CircuitBreaker [" + String(service_name_) + "]: Manual reset → CLOSED");
  failure_count_ = 0;
  transitionTo(CircuitState::CLOSED);
}

// ============================================
// STATUS QUERIES
// ============================================
bool CircuitBreaker::isOpen() const {
  return state_ == CircuitState::OPEN;
}

bool CircuitBreaker::isClosed() const {
  return state_ == CircuitState::CLOSED;
}

CircuitState CircuitBreaker::getState() const {
  return state_;
}

uint8_t CircuitBreaker::getFailureCount() const {
  return failure_count_;
}

const char* CircuitBreaker::getServiceName() const {
  return service_name_;
}

// ============================================
// PRIVATE HELPER METHODS
// ============================================
void CircuitBreaker::transitionTo(CircuitState new_state) {
  CircuitState old_state = state_;
  state_ = new_state;
  state_change_time_ = millis();
  
  // Log state transition
  const char* old_state_str = (old_state == CircuitState::CLOSED) ? "CLOSED" : 
                              (old_state == CircuitState::OPEN) ? "OPEN" : "HALF_OPEN";
  const char* new_state_str = (new_state == CircuitState::CLOSED) ? "CLOSED" : 
                              (new_state == CircuitState::OPEN) ? "OPEN" : "HALF_OPEN";
  
  LOG_D(TAG, "CircuitBreaker [" + String(service_name_) + "]: State transition: " + 
            String(old_state_str) + " → " + String(new_state_str));
}

bool CircuitBreaker::shouldAttemptRecovery() const {
  if (state_ != CircuitState::OPEN) {
    return false;
  }
  
  unsigned long time_since_open = millis() - state_change_time_;
  return time_since_open >= recovery_timeout_ms_;
}

bool CircuitBreaker::halfOpenTestTimedOut() const {
  if (state_ != CircuitState::HALF_OPEN) {
    return false;
  }
  
  unsigned long time_in_halfopen = millis() - state_change_time_;
  return time_in_halfopen >= halfopen_timeout_ms_;
}

