#include "sensor_registry.h"

// ============================================
// SENSOR CAPABILITY REGISTRY
// ============================================
// Central registry of all known sensor types
// Maps ESP32 sensor types to server processor types and device information

// SHT31 Sensor (I2C, Multi-Value: Temp + Humidity)
static const SensorCapability SHT31_TEMP_CAP = {
    .server_sensor_type = "sht31_temp",
    .device_type = "sht31",
    .i2c_address = 0x44,  // Default SHT31 address (0x45 if ADR pin to VIN)
    .is_multi_value = true,
    .is_i2c = true,
    .is_uart = false,
    .is_digital = false,
    .is_pulse = false,
};

static const SensorCapability SHT31_HUMIDITY_CAP = {
    .server_sensor_type = "sht31_humidity",
    .device_type = "sht31",
    .i2c_address = 0x44,
    .is_multi_value = true,
    .is_i2c = true,
    .is_uart = false,
    .is_digital = false,
    .is_pulse = false,
};

// SHT31 Base type — resolves "sht31" from server config to a valid capability
// Server may send base device type; firmware uses isMultiValueDevice() + getMultiValueTypes()
// to resolve sub-types (sht31_temp, sht31_humidity)
static const SensorCapability SHT31_BASE_CAP = {
    .server_sensor_type = "sht31",
    .device_type = "sht31",
    .i2c_address = 0x44,
    .is_multi_value = true,
    .is_i2c = true,
    .is_uart = false,
    .is_digital = false,
    .is_pulse = false,
};

// DS18B20 Sensor (OneWire, Single-Value: Temperature)
static const SensorCapability DS18B20_CAP = {
    .server_sensor_type = "ds18b20",
    .device_type = "ds18b20",
    .i2c_address = 0x00,  // Not I2C
    .is_multi_value = false,
    .is_i2c = false,
    .is_uart = false,
    .is_digital = false,
    .is_pulse = false,
};

// BMP280 Sensor (I2C, Multi-Value: Pressure + Temperature)
static const SensorCapability BMP280_PRESSURE_CAP = {
    .server_sensor_type = "bmp280_pressure",
    .device_type = "bmp280",
    .i2c_address = 0x76,  // Default BMP280 address (0x77 if SDO to VCC)
    .is_multi_value = true,
    .is_i2c = true,
    .is_uart = false,
    .is_digital = false,
    .is_pulse = false,
};

static const SensorCapability BMP280_TEMP_CAP = {
    .server_sensor_type = "bmp280_temp",
    .device_type = "bmp280",
    .i2c_address = 0x76,
    .is_multi_value = true,
    .is_i2c = true,
    .is_uart = false,
    .is_digital = false,
    .is_pulse = false,
};

// BMP280 Base type — resolves "bmp280" from server config
static const SensorCapability BMP280_BASE_CAP = {
    .server_sensor_type = "bmp280",
    .device_type = "bmp280",
    .i2c_address = 0x76,
    .is_multi_value = true,
    .is_i2c = true,
    .is_uart = false,
    .is_digital = false,
    .is_pulse = false,
};

// BME280 Sensor (I2C, Multi-Value: Pressure + Temperature + Humidity)
static const SensorCapability BME280_PRESSURE_CAP = {
    .server_sensor_type = "bme280_pressure",
    .device_type = "bme280",
    .i2c_address = 0x76,  // Default BME280 address (0x77 if SDO to VCC)
    .is_multi_value = true,
    .is_i2c = true,
    .is_uart = false,
    .is_digital = false,
    .is_pulse = false,
};

static const SensorCapability BME280_TEMP_CAP = {
    .server_sensor_type = "bme280_temp",
    .device_type = "bme280",
    .i2c_address = 0x76,
    .is_multi_value = true,
    .is_i2c = true,
    .is_uart = false,
    .is_digital = false,
    .is_pulse = false,
};

static const SensorCapability BME280_HUMIDITY_CAP = {
    .server_sensor_type = "bme280_humidity",
    .device_type = "bme280",
    .i2c_address = 0x76,
    .is_multi_value = true,
    .is_i2c = true,
    .is_uart = false,
    .is_digital = false,
    .is_pulse = false,
};

// BME280 Base type — resolves "bme280" from server config
static const SensorCapability BME280_BASE_CAP = {
    .server_sensor_type = "bme280",
    .device_type = "bme280",
    .i2c_address = 0x76,
    .is_multi_value = true,
    .is_i2c = true,
    .is_uart = false,
    .is_digital = false,
    .is_pulse = false,
};

// pH Sensor (Analog ADC, Single-Value)
static const SensorCapability PH_SENSOR_CAP = {
    .server_sensor_type = "ph",
    .device_type = "ph_sensor",
    .i2c_address = 0x00,  // Not I2C
    .is_multi_value = false,
    .is_i2c = false,
    .is_uart = false,
    .is_digital = false,
    .is_pulse = false,
};

// EC Sensor (Analog ADC, Single-Value)
static const SensorCapability EC_SENSOR_CAP = {
    .server_sensor_type = "ec",
    .device_type = "ec_sensor",
    .i2c_address = 0x00,  // Not I2C
    .is_multi_value = false,
    .is_i2c = false,
    .is_uart = false,
    .is_digital = false,
    .is_pulse = false,
};

// Moisture Sensor (Analog ADC, Single-Value)
static const SensorCapability MOISTURE_CAP = {
    .server_sensor_type = "moisture",
    .device_type = "moisture",
    .i2c_address = 0x00,  // Not I2C
    .is_multi_value = false,
    .is_i2c = false,
    .is_uart = false,
    .is_digital = false,
    .is_pulse = false,
};

// CO2 Sensor (UART MH-Z19 / SEN0220, Single-Value RAW PPM)
static const SensorCapability CO2_CAP = {
    .server_sensor_type = "co2",
    .device_type = "mhz19",
    .i2c_address = 0x00,
    .is_multi_value = false,
    .is_i2c = false,
    .is_uart = true,
    .is_digital = false,
    .is_pulse = false,
};

// Flow sensor (FS300A G3/4, pulse-counting via ISR — raw pulse count, no unit conversion)
static const SensorCapability FLOW_CAP = {
    .server_sensor_type = "flow",
    .device_type        = "flow",
    .i2c_address        = 0x00,
    .is_multi_value     = false,
    .is_i2c             = false,
    .is_uart            = false,
    .is_digital         = false,
    .is_pulse           = true,
};

// Digital level switch (XKC-Y25-NPN, NPN Open-Collector, Active-Low)
static const SensorCapability LIQUID_LEVEL_CAP = {
    .server_sensor_type = "liquid_level",
    .device_type        = "liquid_level",
    .i2c_address        = 0x00,
    .is_multi_value     = false,
    .is_i2c             = false,
    .is_uart            = false,
    .is_digital         = true,
    .is_pulse           = false,
};

// ============================================
// REGISTRY LOOKUP TABLE
// ============================================
// Maps ESP32 sensor types to capabilities
struct SensorTypeMapping {
    const char* esp32_type;
    const SensorCapability* capability;
};

static const SensorTypeMapping SENSOR_TYPE_MAP[] = {
    // SHT31 variants
    {"temperature_sht31", &SHT31_TEMP_CAP},
    {"humidity_sht31", &SHT31_HUMIDITY_CAP},
    {"sht31_temp", &SHT31_TEMP_CAP},  // Already normalized
    {"sht31_humidity", &SHT31_HUMIDITY_CAP},  // Already normalized
    {"sht31", &SHT31_BASE_CAP},  // Base device type (multi-value)
    
    // DS18B20 variants
    {"temperature_ds18b20", &DS18B20_CAP},
    {"ds18b20", &DS18B20_CAP},  // Already normalized
    
    // BMP280 variants
    {"pressure_bmp280", &BMP280_PRESSURE_CAP},
    {"temperature_bmp280", &BMP280_TEMP_CAP},
    {"bmp280_pressure", &BMP280_PRESSURE_CAP},  // Already normalized
    {"bmp280_temp", &BMP280_TEMP_CAP},  // Already normalized
    {"bmp280", &BMP280_BASE_CAP},  // Base device type (multi-value)

    // BME280 variants
    {"pressure_bme280", &BME280_PRESSURE_CAP},
    {"temperature_bme280", &BME280_TEMP_CAP},
    {"humidity_bme280", &BME280_HUMIDITY_CAP},
    {"bme280_pressure", &BME280_PRESSURE_CAP},  // Already normalized
    {"bme280_temp", &BME280_TEMP_CAP},  // Already normalized
    {"bme280_humidity", &BME280_HUMIDITY_CAP},  // Already normalized
    {"bme280", &BME280_BASE_CAP},  // Base device type (multi-value)

    // pH sensor
    {"ph_sensor", &PH_SENSOR_CAP},
    {"ph", &PH_SENSOR_CAP},  // Already normalized
    
    // EC sensor
    {"ec_sensor", &EC_SENSOR_CAP},
    {"ec", &EC_SENSOR_CAP},  // Already normalized
    
    // Moisture sensor
    {"moisture", &MOISTURE_CAP},
    {"soil_moisture", &MOISTURE_CAP},  // Alias — canonical name is "moisture"

    // CO2 (UART MH-Z19 / SEN0220)
    {"co2", &CO2_CAP},
    {"mhz19_co2", &CO2_CAP},

    // Flow sensor (FS300A G3/4 and compatible pulse-output sensors)
    {"flow", &FLOW_CAP},
    {"yfs201", &FLOW_CAP},  // Alias — canonical name is "flow"

    // Digital sensors
    {"liquid_level", &LIQUID_LEVEL_CAP},

    // End marker
    {nullptr, nullptr}
};

// Multi-value device definitions
struct MultiValueDevice {
    const char* device_type;
    const char* value_types[4];  // Max 4 values per device
    uint8_t value_count;
};

static const MultiValueDevice MULTI_VALUE_DEVICES[] = {
    {
        .device_type = "sht31",
        .value_types = {"sht31_temp", "sht31_humidity", nullptr, nullptr},
        .value_count = 2,
    },
    {
        .device_type = "bmp280",
        .value_types = {"bmp280_pressure", "bmp280_temp", nullptr, nullptr},
        .value_count = 2,
    },
    {
        .device_type = "bme280",
        .value_types = {"bme280_pressure", "bme280_temp", "bme280_humidity", nullptr},
        .value_count = 3,
    },
    // End marker
    {nullptr, {nullptr, nullptr, nullptr, nullptr}, 0}
};

// ============================================
// IMPLEMENTATION
// ============================================

const SensorCapability* findSensorCapability(const String& sensor_type) {
    if (sensor_type.length() == 0) {
        return nullptr;
    }
    
    // Case-insensitive lookup
    String lower_type = sensor_type;
    lower_type.toLowerCase();
    
    for (uint8_t i = 0; SENSOR_TYPE_MAP[i].esp32_type != nullptr; i++) {
        if (lower_type == String(SENSOR_TYPE_MAP[i].esp32_type)) {
            return SENSOR_TYPE_MAP[i].capability;
        }
    }
    
    return nullptr;
}

bool isMultiValueDevice(const String& device_type) {
    if (device_type.length() == 0) {
        return false;
    }
    
    String lower_type = device_type;
    lower_type.toLowerCase();
    
    for (uint8_t i = 0; MULTI_VALUE_DEVICES[i].device_type != nullptr; i++) {
        if (lower_type == String(MULTI_VALUE_DEVICES[i].device_type)) {
            return true;
        }
    }
    
    return false;
}

uint8_t getI2CAddress(const String& device_type, uint8_t default_address) {
    const SensorCapability* cap = findSensorCapability(device_type);
    if (cap && cap->is_i2c) {
        return cap->i2c_address;
    }
    
    // Try direct device type lookup
    String lower_type = device_type;
    lower_type.toLowerCase();
    
    for (uint8_t i = 0; MULTI_VALUE_DEVICES[i].device_type != nullptr; i++) {
        if (lower_type == String(MULTI_VALUE_DEVICES[i].device_type)) {
            // Get I2C address from first capability of this device
            const SensorCapability* first_cap = findSensorCapability(
                String(MULTI_VALUE_DEVICES[i].value_types[0])
            );
            if (first_cap && first_cap->is_i2c) {
                return first_cap->i2c_address;
            }
        }
    }
    
    return default_address;
}

String getServerSensorType(const String& esp32_sensor_type) {
    const SensorCapability* cap = findSensorCapability(esp32_sensor_type);
    if (cap) {
        return String(cap->server_sensor_type);
    }
    
    // If not found, return original (might already be normalized)
    return esp32_sensor_type;
}

uint8_t getMultiValueTypes(const String& device_type, String* output, uint8_t max_output) {
    if (output == nullptr || max_output == 0) {
        return 0;
    }
    
    String lower_type = device_type;
    lower_type.toLowerCase();
    
    for (uint8_t i = 0; MULTI_VALUE_DEVICES[i].device_type != nullptr; i++) {
        if (lower_type == String(MULTI_VALUE_DEVICES[i].device_type)) {
            const MultiValueDevice* device = &MULTI_VALUE_DEVICES[i];
            uint8_t count = 0;
            
            for (uint8_t j = 0; j < device->value_count && j < max_output; j++) {
                if (device->value_types[j] != nullptr) {
                    output[count] = String(device->value_types[j]);
                    count++;
                }
            }
            
            return count;
        }
    }
    
    return 0;
}

























