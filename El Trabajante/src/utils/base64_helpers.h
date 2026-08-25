#pragma once
#include <cstddef>
#include <cstdint>

// AUT-1141: minimal base64 DECODE (server encodes, firmware only ever
// decodes — no encode path needed). No lookup table, same flash-conservation
// approach as the project's CRC8 implementation
// (offline_mode_manager.cpp crc8()).
namespace Base64 {

inline int8_t decodeChar(char c) {
    if (c >= 'A' && c <= 'Z') return static_cast<int8_t>(c - 'A');
    if (c >= 'a' && c <= 'z') return static_cast<int8_t>(c - 'a' + 26);
    if (c >= '0' && c <= '9') return static_cast<int8_t>(c - '0' + 52);
    if (c == '+') return 62;
    if (c == '/') return 63;
    return -1;  // padding '=' or invalid character
}

// Decodes a NUL-terminated base64 string into out[]. Returns the number of
// decoded bytes, or 0 on malformed input / insufficient out_capacity.
inline size_t decode(const char* in, uint8_t* out, size_t out_capacity) {
    if (in == nullptr || out == nullptr) return 0;
    size_t in_len = 0;
    while (in[in_len] != '\0') in_len++;
    if (in_len == 0 || (in_len % 4) != 0) return 0;

    size_t out_len = 0;
    for (size_t i = 0; i < in_len; i += 4) {
        const bool pad2 = (in[i + 2] == '=');
        const bool pad3 = (in[i + 3] == '=');
        const int8_t v0 = decodeChar(in[i]);
        const int8_t v1 = decodeChar(in[i + 1]);
        const int8_t v2 = pad2 ? 0 : decodeChar(in[i + 2]);
        const int8_t v3 = pad3 ? 0 : decodeChar(in[i + 3]);
        if (v0 < 0 || v1 < 0 || (!pad2 && v2 < 0) || (!pad3 && v3 < 0)) return 0;
        // '=' padding may only appear as the last one or two characters.
        if (pad2 && i + 4 != in_len) return 0;
        if (pad3 && pad2) return 0;

        if (out_len >= out_capacity) return 0;
        out[out_len++] = static_cast<uint8_t>((v0 << 2) | (v1 >> 4));

        if (!pad2) {
            if (out_len >= out_capacity) return 0;
            out[out_len++] = static_cast<uint8_t>((v1 << 4) | (v2 >> 2));

            if (!pad3) {
                if (out_len >= out_capacity) return 0;
                out[out_len++] = static_cast<uint8_t>((v2 << 6) | v3);
            }
        }
    }
    return out_len;
}

}  // namespace Base64
