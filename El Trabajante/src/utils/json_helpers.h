#ifndef UTILS_JSON_HELPERS_H
#define UTILS_JSON_HELPERS_H

#include <Arduino.h>
#include <ArduinoJson.h>

#include "logger.h"

namespace JsonHelpers {

// Header-local TAG (not static to avoid shadowing issues in including .cpp files)
namespace { const char* const JSON_TAG = "JSON"; }

inline bool extractInt(const JsonObjectConst& obj, const char* key, int& out, int default_val = 0) {
  if (!obj.containsKey(key)) {
    out = default_val;
    return false;
  }

  JsonVariantConst value = obj[key];
  if (value.is<long>() || value.is<int>() || value.is<float>() || value.is<double>()) {
    out = value.as<int>();
    return true;
  }

  LOG_W(JSON_TAG, "JSON key '" + String(key) + "' is not an integer");
  out = default_val;
  return false;
}

inline bool extractString(const JsonObjectConst& obj,
                          const char* key,
                          String& out,
                          const String& default_val = "") {
  if (!obj.containsKey(key)) {
    out = default_val;
    return false;
  }

  JsonVariantConst value = obj[key];
  if (value.is<const char*>() || value.is<String>()) {
    out = String(value.as<const char*>());
    return true;
  }

  LOG_W(JSON_TAG, "JSON key '" + String(key) + "' is not a string");
  out = default_val;
  return false;
}

inline bool extractBool(const JsonObjectConst& obj, const char* key, bool& out, bool default_val = false) {
  if (!obj.containsKey(key)) {
    out = default_val;
    return false;
  }

  JsonVariantConst value = obj[key];
  if (value.is<bool>()) {
    out = value.as<bool>();
    return true;
  }
  if (value.is<int>() || value.is<long>()) {
    int temp = value.as<int>();
    out = temp != 0;
    return true;
  }
  if (value.is<const char*>()) {
    String str = value.as<const char*>();
    str.toLowerCase();
    if (str == "true" || str == "1") {
      out = true;
      return true;
    }
    if (str == "false" || str == "0") {
      out = false;
      return true;
    }
  }

  LOG_W(JSON_TAG, "JSON key '" + String(key) + "' is not a boolean");
  out = default_val;
  return false;
}

}  // namespace JsonHelpers

#endif  // UTILS_JSON_HELPERS_H

