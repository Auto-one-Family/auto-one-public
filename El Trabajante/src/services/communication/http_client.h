#ifndef SERVICES_COMMUNICATION_HTTP_CLIENT_H
#define SERVICES_COMMUNICATION_HTTP_CLIENT_H

#include <Arduino.h>
#include <WiFiClient.h>

// ============================================
// HTTP CLIENT CLASS (Phase 4 - Communication Layer)
// ============================================
// Purpose: HTTP client for communication with God-Kaiser Server
// - POST/GET requests
// - URL parsing (IP:Port or Hostname)
// - Error handling and timeout management
// - Response parsing

// Forward declarations
class WiFiManager;

// ============================================
// HTTP RESPONSE STRUCTURE
// ============================================
struct HTTPResponse {
    int status_code = 0;
    String body;
    bool success = false;
    char error_message[128] = {0};
};

// ============================================
// HTTP CLIENT CLASS
// ============================================
class HTTPClient {
public:
    // ============================================
    // SINGLETON PATTERN
    // ============================================
    static HTTPClient& getInstance();
    
    // ============================================
    // LIFECYCLE MANAGEMENT
    // ============================================
    // Initialize HTTP client
    bool begin();
    
    // Deinitialize HTTP client
    void end();
    
    // ============================================
    // HTTP REQUESTS
    // ============================================
    // POST Request (Primary API - const char*)
    HTTPResponse post(const char* url, const char* payload, 
                     const char* content_type = "application/json",
                     int timeout_ms = 5000);
    
    // Convenience Wrapper: String (Kompatibilität)
    inline HTTPResponse post(const String& url, const String& payload,
                            const String& content_type = "application/json",
                            int timeout_ms = 5000) {
        return post(url.c_str(), payload.c_str(), content_type.c_str(), timeout_ms);
    }
    
    // GET Request (optional, für Library-Download in Phase 8)
    HTTPResponse get(const char* url, int timeout_ms = 5000);
    
    inline HTTPResponse get(const String& url, int timeout_ms = 5000) {
        return get(url.c_str(), timeout_ms);
    }
    
    // ============================================
    // STATUS QUERIES
    // ============================================
    bool isInitialized() const { return initialized_; }
    void setTimeout(int timeout_ms) { timeout_ms_ = timeout_ms; }
    int getTimeout() const { return timeout_ms_; }
    
private:
    // ============================================
    // PRIVATE CONSTRUCTOR (SINGLETON)
    // ============================================
    HTTPClient();
    ~HTTPClient();
    
    // Prevent copy
    HTTPClient(const HTTPClient&) = delete;
    HTTPClient& operator=(const HTTPClient&) = delete;
    
    // ============================================
    // PRIVATE MEMBERS
    // ============================================
    WiFiClient wifi_client_;
    int timeout_ms_ = 5000;
    bool initialized_ = false;
    
    // ============================================
    // HELPER METHODS
    // ============================================
    // Parse URL into host, port, and path
    bool parseUrl(const char* url, char* host, size_t host_len, 
                  uint16_t& port, char* path, size_t path_len);
    
    // Send HTTP request and read response
    HTTPResponse sendRequest(const char* method, const char* host, uint16_t port,
                            const char* path, const char* payload,
                            const char* content_type, int timeout_ms);
    
    // Read HTTP response headers and body
    bool readResponse(HTTPResponse& response, int timeout_ms);
    
    // Extract status code from response line
    int parseStatusCode(const char* status_line);
};

// ============================================
// GLOBAL HTTP CLIENT INSTANCE
// ============================================
extern HTTPClient& httpClient;

#endif // SERVICES_COMMUNICATION_HTTP_CLIENT_H

