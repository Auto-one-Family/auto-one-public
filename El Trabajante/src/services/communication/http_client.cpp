#include "http_client.h"
#include "wifi_manager.h"
#include "../../utils/logger.h"
#include "../../error_handling/error_tracker.h"
#include "../../models/error_codes.h"

// ESP-IDF TAG convention for structured logging
static const char* TAG = "HTTP";

// ============================================
// GLOBAL HTTP CLIENT INSTANCE
// ============================================
HTTPClient& httpClient = HTTPClient::getInstance();

// ============================================
// SINGLETON IMPLEMENTATION
// ============================================
HTTPClient& HTTPClient::getInstance() {
    static HTTPClient instance;
    return instance;
}

// ============================================
// PRIVATE CONSTRUCTOR
// ============================================
HTTPClient::HTTPClient() 
    : timeout_ms_(5000),
      initialized_(false) {
}

HTTPClient::~HTTPClient() {
    end();
}

// ============================================
// LIFECYCLE: INITIALIZATION
// ============================================
bool HTTPClient::begin() {
    if (initialized_) {
        LOG_W(TAG, "HTTPClient already initialized");
        return true;
    }
    
    LOG_I(TAG, "HTTPClient: Initializing...");
    
    initialized_ = true;
    
    LOG_I(TAG, "HTTPClient: Initialized");
    return true;
}

// ============================================
// LIFECYCLE: DEINITIALIZATION
// ============================================
void HTTPClient::end() {
    if (!initialized_) {
        return;
    }
    
    if (wifi_client_.connected()) {
        wifi_client_.stop();
    }
    
    initialized_ = false;
    LOG_I(TAG, "HTTPClient: Deinitialized");
}

// ============================================
// HTTP POST REQUEST
// ============================================
HTTPResponse HTTPClient::post(const char* url, const char* payload, 
                              const char* content_type, int timeout_ms) {
    HTTPResponse response;
    
    if (!initialized_) {
        strncpy(response.error_message, "HTTPClient not initialized", sizeof(response.error_message) - 1);
        errorTracker.trackError(ERROR_HTTP_INIT_FAILED, ERROR_SEVERITY_ERROR, 
                               "HTTPClient not initialized");
        return response;
    }
    
    // Check WiFi connection
    WiFiManager& wifi = WiFiManager::getInstance();
    if (!wifi.isConnected()) {
        strncpy(response.error_message, "WiFi not connected", sizeof(response.error_message) - 1);
        errorTracker.trackError(ERROR_WIFI_DISCONNECT, ERROR_SEVERITY_ERROR, 
                               "WiFi not connected for HTTP request");
        return response;
    }
    
    // Parse URL
    char host[256] = {0};
    uint16_t port = 80;
    char path[256] = {0};
    
    if (!parseUrl(url, host, sizeof(host), port, path, sizeof(path))) {
        strncpy(response.error_message, "Invalid URL format", sizeof(response.error_message) - 1);
        errorTracker.trackError(ERROR_HTTP_REQUEST_FAILED, ERROR_SEVERITY_ERROR, 
                               "Invalid URL format");
        return response;
    }
    
    // Use provided timeout or default
    int actual_timeout = (timeout_ms > 0) ? timeout_ms : timeout_ms_;
    
    // Send POST request
    response = sendRequest("POST", host, port, path, payload, content_type, actual_timeout);
    
    return response;
}

// ============================================
// HTTP GET REQUEST
// ============================================
HTTPResponse HTTPClient::get(const char* url, int timeout_ms) {
    HTTPResponse response;
    
    if (!initialized_) {
        strncpy(response.error_message, "HTTPClient not initialized", sizeof(response.error_message) - 1);
        errorTracker.trackError(ERROR_HTTP_INIT_FAILED, ERROR_SEVERITY_ERROR, 
                               "HTTPClient not initialized");
        return response;
    }
    
    // Check WiFi connection
    WiFiManager& wifi = WiFiManager::getInstance();
    if (!wifi.isConnected()) {
        strncpy(response.error_message, "WiFi not connected", sizeof(response.error_message) - 1);
        errorTracker.trackError(ERROR_WIFI_DISCONNECT, ERROR_SEVERITY_ERROR, 
                               "WiFi not connected for HTTP request");
        return response;
    }
    
    // Parse URL
    char host[256] = {0};
    uint16_t port = 80;
    char path[256] = {0};
    
    if (!parseUrl(url, host, sizeof(host), port, path, sizeof(path))) {
        strncpy(response.error_message, "Invalid URL format", sizeof(response.error_message) - 1);
        errorTracker.trackError(ERROR_HTTP_REQUEST_FAILED, ERROR_SEVERITY_ERROR, 
                               "Invalid URL format");
        return response;
    }
    
    // Use provided timeout or default
    int actual_timeout = (timeout_ms > 0) ? timeout_ms : timeout_ms_;
    
    // Send GET request
    response = sendRequest("GET", host, port, path, nullptr, nullptr, actual_timeout);
    
    return response;
}

// ============================================
// URL PARSING
// ============================================
bool HTTPClient::parseUrl(const char* url, char* host, size_t host_len, 
                          uint16_t& port, char* path, size_t path_len) {
    if (!url || !host || !path) {
        return false;
    }
    
    // Initialize outputs
    memset(host, 0, host_len);
    memset(path, 0, path_len);
    port = 80;  // Default HTTP port
    
    // Skip http:// or https:// prefix
    const char* url_start = url;
    if (strncmp(url, "http://", 7) == 0) {
        url_start = url + 7;
    } else if (strncmp(url, "https://", 8) == 0) {
        url_start = url + 8;
        port = 443;  // Default HTTPS port
    }
    
    // Find path separator
    const char* path_start = strchr(url_start, '/');
    if (path_start) {
        // Copy path
        size_t path_len_actual = strlen(path_start);
        if (path_len_actual >= path_len) {
            path_len_actual = path_len - 1;
        }
        strncpy(path, path_start, path_len_actual);
        path[path_len_actual] = '\0';
    } else {
        // No path, use root
        strncpy(path, "/", path_len - 1);
        path[1] = '\0';
    }
    
    // Extract host:port
    size_t host_len_actual = (path_start) ? (path_start - url_start) : strlen(url_start);
    if (host_len_actual >= host_len) {
        host_len_actual = host_len - 1;
    }
    
    char host_port[256] = {0};
    strncpy(host_port, url_start, host_len_actual);
    host_port[host_len_actual] = '\0';
    
    // Check for port in host:port
    const char* colon = strchr(host_port, ':');
    if (colon) {
        // Extract host
        size_t host_part_len = colon - host_port;
        if (host_part_len >= host_len) {
            host_part_len = host_len - 1;
        }
        strncpy(host, host_port, host_part_len);
        host[host_part_len] = '\0';
        
        // Extract port
        port = (uint16_t)atoi(colon + 1);
        if (port == 0) {
            return false;  // Invalid port
        }
    } else {
        // No port specified, use default
        strncpy(host, host_port, host_len - 1);
        host[host_len - 1] = '\0';
    }
    
    return true;
}

// ============================================
// SEND HTTP REQUEST
// ============================================
HTTPResponse HTTPClient::sendRequest(const char* method, const char* host, uint16_t port,
                                     const char* path, const char* payload,
                                     const char* content_type, int timeout_ms) {
    HTTPResponse response;
    
    // Set read timeout BEFORE connect (used by connect() internally on ESP32)
    wifi_client_.setTimeout(timeout_ms);

    // Connect to server WITH TIMEOUT (ESP32 WiFiClient supports connect(host, port, timeout_ms))
    // This prevents indefinite blocking when server is unreachable
    yield();  // Feed watchdog before potentially blocking operation
    if (!wifi_client_.connect(host, port, timeout_ms)) {
        snprintf(response.error_message, sizeof(response.error_message) - 1,
                "Connection failed (timeout %dms)", timeout_ms);
        errorTracker.trackError(ERROR_HTTP_REQUEST_FAILED, ERROR_SEVERITY_ERROR,
                               "HTTP connection failed/timeout");
        return response;
    }
    yield();  // Feed watchdog after connect
    
    // Build request
    String request;
    request.reserve(512);
    
    // Request line
    request += method;
    request += " ";
    request += path;
    request += " HTTP/1.1\r\n";
    
    // Headers
    request += "Host: ";
    request += host;
    if (port != 80 && port != 443) {
        request += ":";
        request += String(port);
    }
    request += "\r\n";
    
    if (payload && strcmp(method, "POST") == 0) {
        request += "Content-Type: ";
        request += (content_type) ? content_type : "application/json";
        request += "\r\n";
        request += "Content-Length: ";
        request += String(strlen(payload));
        request += "\r\n";
    }
    
    request += "Connection: close\r\n";
    request += "\r\n";
    
    // Send request
    wifi_client_.print(request);
    
    // Send payload if POST
    if (payload && strcmp(method, "POST") == 0) {
        wifi_client_.print(payload);
    }
    
    // Read response
    unsigned long start_time = millis();
    bool response_ok = false;
    
    while (millis() - start_time < (unsigned long)timeout_ms) {
        if (wifi_client_.available()) {
            response_ok = readResponse(response, timeout_ms);
            break;
        }
        yield();  // Feed watchdog while waiting for response
        delay(10);
    }
    
    if (!response_ok) {
        if (wifi_client_.connected()) {
            strncpy(response.error_message, "Timeout waiting for response", sizeof(response.error_message) - 1);
            errorTracker.trackError(ERROR_HTTP_TIMEOUT, ERROR_SEVERITY_ERROR, 
                                   "HTTP response timeout");
        } else {
            strncpy(response.error_message, "Connection lost", sizeof(response.error_message) - 1);
            errorTracker.trackError(ERROR_CONNECTION_LOST, ERROR_SEVERITY_ERROR, 
                                   "HTTP connection lost");
        }
    }
    
    // Close connection
    wifi_client_.stop();
    
    return response;
}

// ============================================
// READ HTTP RESPONSE
// ============================================
bool HTTPClient::readResponse(HTTPResponse& response, int timeout_ms) {
    unsigned long start_time = millis();
    String status_line = "";
    bool headers_complete = false;
    bool body_started = false;
    int content_length = -1;
    
    response.body.reserve(1024);  // Reserve 1KB for response body
    
    // Read response line by line
    while (millis() - start_time < (unsigned long)timeout_ms) {
        if (!wifi_client_.available()) {
            yield();  // Feed watchdog while waiting for more data
            delay(10);
            continue;
        }
        
        String line = wifi_client_.readStringUntil('\n');
        line.trim();
        
        if (line.length() == 0) {
            if (!headers_complete) {
                headers_complete = true;
                body_started = true;
                continue;
            } else if (body_started) {
                // End of body
                break;
            }
        }
        
        if (!headers_complete) {
            // Parse status line
            if (status_line.length() == 0) {
                status_line = line;
                response.status_code = parseStatusCode(line.c_str());
            }
            
            // Parse Content-Length header
            if (line.startsWith("Content-Length:")) {
                content_length = line.substring(15).toInt();
            }
        } else if (body_started) {
            // Read body
            response.body += line;
            if (content_length > 0 && (int)response.body.length() >= content_length) {
                break;
            }
        }
    }
    
    // Check if we got a valid response
    if (response.status_code == 0) {
        return false;
    }
    
    // Success if status code is 2xx
    response.success = (response.status_code >= 200 && response.status_code < 300);
    
    if (!response.success) {
        snprintf(response.error_message, sizeof(response.error_message), 
                "HTTP %d", response.status_code);
        errorTracker.trackError(ERROR_HTTP_RESPONSE_INVALID, ERROR_SEVERITY_ERROR, 
                               response.error_message);
    }
    
    return true;
}

// ============================================
// PARSE STATUS CODE
// ============================================
int HTTPClient::parseStatusCode(const char* status_line) {
    if (!status_line) {
        return 0;
    }
    
    // HTTP/1.1 200 OK
    // Find first space
    const char* space = strchr(status_line, ' ');
    if (!space) {
        return 0;
    }
    
    // Find second space (or end of line)
    const char* code_start = space + 1;
    const char* code_end = strchr(code_start, ' ');
    if (!code_end) {
        code_end = code_start + strlen(code_start);
    }
    
    // Extract status code
    char code_str[4] = {0};
    size_t code_len = code_end - code_start;
    if (code_len >= sizeof(code_str)) {
        code_len = sizeof(code_str) - 1;
    }
    strncpy(code_str, code_start, code_len);
    code_str[code_len] = '\0';
    
    return atoi(code_str);
}

