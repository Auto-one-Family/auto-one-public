#ifndef MOCK_ARDUINO_H
#define MOCK_ARDUINO_H

#ifdef NATIVE_TEST

#include <cstdint>
#include <cstring>
#include <cstdio>
#include <string>

// ============================================
// GPIO CONSTANTS (ESP32 Arduino values)
// ============================================
#define INPUT          0x01
#define OUTPUT         0x03
#define INPUT_PULLUP   0x05
#define INPUT_PULLDOWN 0x09
#define HIGH           1
#define LOW            0

// ============================================
// ARDUINO STRING CLASS MOCK
// ============================================
// Minimal String implementation for native tests
// Only implements features actually used by firmware

class String {
public:
    String() : data_("") {}
    String(const char* str) : data_(str ? str : "") {}
    String(int val) : data_(std::to_string(val)) {}
    String(unsigned long val) : data_(std::to_string(val)) {}
    String(float val) {
        char buf[16];
        snprintf(buf, sizeof(buf), "%.2f", val);
        data_ = buf;
    }

    const char* c_str() const { return data_.c_str(); }
    size_t length() const { return data_.length(); }

    bool operator==(const String& other) const { return data_ == other.data_; }
    bool operator==(const char* other) const { return data_ == other; }
    bool operator!=(const String& other) const { return data_ != other.data_; }
    bool operator<(const String& other) const { return data_ < other.data_; }
    String operator+(const String& other) const {
        return String((data_ + other.data_).c_str());
    }
    String operator+(const char* other) const {
        return String((data_ + std::string(other ? other : "")).c_str());
    }
    String& operator+=(const String& other) {
        data_ += other.data_;
        return *this;
    }
    String& operator+=(const char* other) {
        if (other) data_ += other;
        return *this;
    }

    // Allow access from non-member operator+
    friend inline String operator+(const char* lhs, const String& rhs);

private:
    std::string data_;
};

// Non-member operator+ for "const char*" + String concatenation
inline String operator+(const char* lhs, const String& rhs) {
    return String((std::string(lhs ? lhs : "") + rhs.data_).c_str());
}

// ============================================
// ARDUINO API MOCK FUNCTIONS
// ============================================

inline unsigned long millis() { return 0; }
inline void delay(unsigned long ms) { (void)ms; }
inline void delayMicroseconds(unsigned long us) { (void)us; }

// ============================================
// SERIAL MOCK (no-op)
// ============================================
// Serial is not used in Pure-Logic tests

class SerialMock {
public:
    void begin(unsigned long baud) { (void)baud; }
    void println(const char* str) { (void)str; }
    template<typename T>
    void println(T value) { (void)value; }
    template<typename... Args>
    void printf(const char* fmt, Args... args) {
        (void)fmt;
        ((void)args, ...);
    }
};
inline SerialMock Serial;

#endif // NATIVE_TEST
#endif // MOCK_ARDUINO_H
