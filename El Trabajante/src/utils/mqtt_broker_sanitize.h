#pragma once

#include <Arduino.h>
#include <cctype>

/**
 * Normalisiert NVS-/Portal-Werte für den ESP-IDF-MQTT-Client.
 *
 * Verhindert u. a. `mqtt://:192.168.x.x` (esp-tls: couldn't get hostname for :192.168…),
 * wenn `server_address` fälschlich ein Schema oder führende Doppelpunkte enthält.
 *
 * @param host in/out Hostname oder IPv4 (ohne mqtt://, ohne :port)
 * @param mqtt_port optional; wenn im Host-String `:port` erkannt wird (IPv4), wird er übernommen
 */
inline void sanitizeMqttBrokerHostAndPort(String& host, uint16_t* mqtt_port) {
  host.trim();

  while (host.length() > 0 && host.charAt(0) == ':') {
    host.remove(0, 1);
  }

  if (host.length() >= 7 && host.substring(0, 7).equalsIgnoreCase("mqtt://")) {
    host = host.substring(7);
  } else if (host.length() >= 8 && host.substring(0, 8).equalsIgnoreCase("mqtts://")) {
    host = host.substring(8);
  }

  while (host.length() > 0 && (host.charAt(0) == '/' || host.charAt(0) == ':')) {
    host.remove(0, 1);
  }
  host.trim();

  while (host.length() > 0 && host.endsWith("/")) {
    host.remove(host.length() - 1);
  }
  host.trim();

  // IPv6 in eckigen Klammern: Port-Split überspringen
  if (host.indexOf('[') >= 0) {
    return;
  }

  const int last_colon = host.lastIndexOf(':');
  if (last_colon > 0 && mqtt_port != nullptr) {
    const String maybe_port = host.substring(last_colon + 1);
    bool all_digits = maybe_port.length() > 0;
    for (unsigned i = 0; all_digits && i < maybe_port.length(); i++) {
      const char c = static_cast<char>(maybe_port.charAt(i));
      if (!std::isdigit(static_cast<unsigned char>(c))) {
        all_digits = false;
      }
    }
    if (all_digits) {
      const long p = maybe_port.toInt();
      if (p > 0 && p <= 65535) {
        *mqtt_port = static_cast<uint16_t>(p);
        host = host.substring(0, last_colon);
        host.trim();
      }
    }
  }
}
