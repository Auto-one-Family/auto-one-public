#ifndef UTILS_ONEWIRE_UTILS_H
#define UTILS_ONEWIRE_UTILS_H

#include <Arduino.h>

// ============================================
// ONEWIRE UTILITY FUNCTIONS
// ============================================
// Purpose: Helper functions for OneWire ROM-Code conversion
// - ROM to Hex-String conversion (for MQTT payloads)
// - Hex-String to ROM conversion (for NVS loading)
// - CRC validation (OneWire standard CRC8)
//
// ROM-Code Format:
// - Array: uint8_t rom[8] = {0x28, 0xFF, 0x64, ...}
// - String: "28FF641E8D3C0C79" (16 hex chars, no separators)
//
// Family Codes (byte 0):
// - 0x28: DS18B20 (most common)
// - 0x10: DS18S20 (legacy)
// - 0x22: DS1822

namespace OneWireUtils {

// ============================================
// ROM-CODE CONVERSION
// ============================================

/**
 * Convert ROM-Code to Hex-String
 * 
 * @param rom 8-byte ROM-Code array
 * @return Hex-String (16 chars uppercase, e.g. "28FF641E8D3C0C79")
 * 
 * Example:
 *   uint8_t rom[8] = {0x28, 0xFF, 0x64, 0x1E, 0x8D, 0x3C, 0x0C, 0x79};
 *   String hex = romToHexString(rom);  // "28FF641E8D3C0C79"
 */
String romToHexString(const uint8_t rom[8]);

/**
 * Convert Hex-String to ROM-Code
 * 
 * @param hex Hex-String (16 chars, e.g. "28FF641E8D3C0C79")
 * @param rom Output: 8-byte ROM-Code array
 * @return true if conversion successful, false if invalid format
 * 
 * Example:
 *   uint8_t rom[8];
 *   bool ok = hexStringToRom("28FF641E8D3C0C79", rom);
 */
bool hexStringToRom(const String& hex, uint8_t rom[8]);

// ============================================
// ROM-CODE VALIDATION
// ============================================

/**
 * Validate ROM-Code using CRC8
 * 
 * @param rom 8-byte ROM-Code array
 * @return true if CRC valid (byte 7 matches calculated CRC)
 * 
 * OneWire CRC8: Polynomial x^8 + x^5 + x^4 + 1
 * ROM structure: [Family][Serial 6 bytes][CRC]
 */
bool isValidRom(const uint8_t rom[8]);

/**
 * Get device type from Family-Code (byte 0)
 * 
 * @param rom 8-byte ROM-Code array
 * @return Device type string ("ds18b20", "ds18s20", "ds1822", "unknown")
 */
String getDeviceType(const uint8_t rom[8]);

}  // namespace OneWireUtils

#endif  // UTILS_ONEWIRE_UTILS_H
