# Hardware Validation Test Suite
# Tests all 4 critical fixes: I2C validation, Input-Only protection, I2C pin protection, ESP model awareness
# Date: 2026-01-14
# Status: Comprehensive Testing Phase

$ErrorActionPreference = "Stop"
$baseUrl = "http://localhost:8000"
$apiBase = "$baseUrl/api/v1"

# Test results tracking
$script:testResults = @()
$script:passed = 0
$script:failed = 0
$script:authToken = $null

function Write-TestResult {
    param(
        [string]$TestName,
        [bool]$Passed,
        [string]$Expected,
        [string]$Actual,
        [string]$Details = ""
    )
    
    $status = if ($Passed) { "✅ PASS" } else { "❌ FAIL" }
    Write-Host "`n[$status] $TestName" -ForegroundColor $(if ($Passed) { "Green" } else { "Red" })
    
    if (-not $Passed) {
        Write-Host "  Expected: $Expected" -ForegroundColor Yellow
        Write-Host "  Actual: $Actual" -ForegroundColor Yellow
        if ($Details) {
            Write-Host "  Details: $Details" -ForegroundColor Yellow
        }
    }
    
    $script:testResults += @{
        TestName = $TestName
        Passed = $Passed
        Expected = $Expected
        Actual = $Actual
        Details = $Details
    }
    
    if ($Passed) {
        $script:passed++
    } else {
        $script:failed++
    }
}

function Invoke-TestRequest {
    param(
        [string]$Method = "POST",
        [string]$Url,
        [hashtable]$Body = $null,
        [int]$ExpectedStatus = 200,
        [bool]$RequireAuth = $true
    )
    
    try {
        $headers = @{
            "Content-Type" = "application/json"
        }
        
        if ($RequireAuth -and $script:authToken) {
            $headers["Authorization"] = "Bearer $script:authToken"
        }
        
        if ($Body) {
            $jsonBody = $Body | ConvertTo-Json -Depth 10
            $response = Invoke-WebRequest -Uri $Url -Method $Method -Headers $headers -Body $jsonBody -ErrorAction Stop
        } else {
            $response = Invoke-WebRequest -Uri $Url -Method $Method -Headers $headers -ErrorAction Stop
        }
        
        return @{
            StatusCode = $response.StatusCode
            Content = $response.Content | ConvertFrom-Json
            Success = $true
        }
    } catch {
        $statusCode = $_.Exception.Response.StatusCode.value__
        $errorContent = ""
        try {
            $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
            $errorContent = $reader.ReadToEnd() | ConvertFrom-Json
        } catch {
            $errorContent = $_.Exception.Message
        }
        
        return @{
            StatusCode = $statusCode
            Content = $errorContent
            Success = $false
        }
    }
}

function Get-AuthToken {
    param(
        [string]$Username = "testadmin",
        [string]$Password = $env:E2E_TEST_PASSWORD
    )
    
    Write-Host "Authenticating as $Username..." -ForegroundColor Yellow
    
    # Try to login
    $loginBody = @{
        username = $Username
        password = $Password
    }
    
    $loginResult = Invoke-TestRequest -Url "$apiBase/auth/login" -Body $loginBody -RequireAuth $false
    
    if ($loginResult.StatusCode -eq 200 -and $loginResult.Content.access_token) {
        $script:authToken = $loginResult.Content.access_token
        Write-Host "✅ Authentication successful" -ForegroundColor Green
        return $true
    }
    
    # If login fails, try to register
    Write-Host "Login failed, attempting to register user..." -ForegroundColor Yellow
    $registerBody = @{
        username = $Username
        email = "$Username@test.local"
        password = $Password
        full_name = "Test User"
    }
    
    $registerResult = Invoke-TestRequest -Url "$apiBase/auth/register" -Body $registerBody -RequireAuth $false
    
    if ($registerResult.StatusCode -eq 201) {
        # Try login again
        $loginResult = Invoke-TestRequest -Url "$apiBase/auth/login" -Body $loginBody -RequireAuth $false
        if ($loginResult.StatusCode -eq 200 -and $loginResult.Content.access_token) {
            $script:authToken = $loginResult.Content.access_token
            Write-Host "✅ User registered and authenticated" -ForegroundColor Green
            return $true
        }
    }
    
    Write-Host "❌ Authentication failed. Status: $($loginResult.StatusCode)" -ForegroundColor Red
    return $false
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Hardware Validation Test Suite" -ForegroundColor Cyan
Write-Host "17 Test Cases - 4 Critical Fixes" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# Check if server is running
Write-Host "`nChecking server availability..." -ForegroundColor Yellow
try {
    $healthCheck = Invoke-WebRequest -Uri "$baseUrl/health" -Method GET -ErrorAction Stop
    Write-Host "✅ Server is running" -ForegroundColor Green
} catch {
    Write-Host "❌ Server is not running on $baseUrl" -ForegroundColor Red
    Write-Host "Please start the server first!" -ForegroundColor Red
    exit 1
}

# Authenticate
if (-not (Get-AuthToken)) {
    Write-Host "`n❌ Failed to authenticate. Cannot proceed with tests." -ForegroundColor Red
    Write-Host "Please ensure the server is running and authentication is configured." -ForegroundColor Yellow
    exit 1
}

# =============================================================================
# Setup: Create test ESP devices
# =============================================================================
Write-Host "`n=== Setup: Creating test ESP devices ===" -ForegroundColor Cyan

# Create ESP_00000001 (WROOM)
$esp1Body = @{
    esp_id = "ESP_00000001"
    hardware_type = "ESP32_WROOM"
    zone_id = "test_zone"
}
$esp1Result = Invoke-TestRequest -Url "$apiBase/esps" -Body $esp1Body -ExpectedStatus 201
if ($esp1Result.StatusCode -eq 201 -or $esp1Result.StatusCode -eq 409) {
    Write-Host "✅ ESP_00000001 ready" -ForegroundColor Green
} else {
    Write-Host "⚠️  ESP_00000001 creation: Status $($esp1Result.StatusCode)" -ForegroundColor Yellow
}

# Create ESP_C3_TEST (C3)
$espC3Body = @{
    esp_id = "ESP_C3_TEST"
    hardware_type = "XIAO_ESP32_C3"
    zone_id = "test_zone"
}
$espC3Result = Invoke-TestRequest -Url "$apiBase/esps" -Body $espC3Body -ExpectedStatus 201
if ($espC3Result.StatusCode -eq 201 -or $espC3Result.StatusCode -eq 409) {
    Write-Host "✅ ESP_C3_TEST ready" -ForegroundColor Green
} else {
    Write-Host "⚠️  ESP_C3_TEST creation: Status $($espC3Result.StatusCode)" -ForegroundColor Yellow
}

# Create ESP_UNKNOWN (for test 4.6)
$espUnknownBody = @{
    esp_id = "ESP_UNKNOWN"
    hardware_type = "ESP32_XYZ_UNKNOWN"
    zone_id = "test_zone"
}
$espUnknownResult = Invoke-TestRequest -Url "$apiBase/esps" -Body $espUnknownBody -ExpectedStatus 201
if ($espUnknownResult.StatusCode -eq 201 -or $espUnknownResult.StatusCode -eq 409) {
    Write-Host "✅ ESP_UNKNOWN ready" -ForegroundColor Green
} else {
    Write-Host "⚠️  ESP_UNKNOWN creation: Status $($espUnknownResult.StatusCode)" -ForegroundColor Yellow
}

# =============================================================================
# Section 2.1: Fix #1 - I2C Address Validation (5 Tests)
# =============================================================================
Write-Host "`n=== Section 2.1: I2C Address Validation ===" -ForegroundColor Cyan

# Test 1.1: Negative I2C Address
Write-Host "`nTest 1.1: Negative I2C address (-1)" -ForegroundColor Yellow
$test1_1 = Invoke-TestRequest -Url "$apiBase/sensors/ESP_00000001/NULL" -Body @{
    sensor_type = "sht31_temp"
    sensor_name = "SHT31 Temp"
    interface_type = "I2C"
    i2c_address = -1
    enabled = $true
    pi_enhanced = $true
} -ExpectedStatus 400

$passed = ($test1_1.StatusCode -eq 400) -and ($test1_1.Content.detail -like "*must be positive*" -or $test1_1.Content.detail -like "*negative*")
Write-TestResult -TestName "1.1: Negative I2C address" -Passed $passed `
    -Expected "400 Bad Request: 'i2c_address must be positive, got -1'" `
    -Actual "Status: $($test1_1.StatusCode), Detail: $($test1_1.Content.detail)"

# Test 1.2: I2C Address > 7-bit (255)
Write-Host "`nTest 1.2: I2C address > 7-bit (255)" -ForegroundColor Yellow
$test1_2 = Invoke-TestRequest -Url "$apiBase/sensors/ESP_00000001/NULL" -Body @{
    sensor_type = "sht31_temp"
    sensor_name = "SHT31"
    interface_type = "I2C"
    i2c_address = 255
} -ExpectedStatus 400

$passed = ($test1_2.StatusCode -eq 400) -and ($test1_2.Content.detail -like "*exceeds 7-bit*" -or $test1_2.Content.detail -like "*0xFF*" -or $test1_2.Content.detail -like "*out of range*")
Write-TestResult -TestName "1.2: I2C address > 7-bit" -Passed $passed `
    -Expected "400 Bad Request: 'i2c_address must be in 7-bit range (0x00-0x7F), got 0xFF'" `
    -Actual "Status: $($test1_2.StatusCode), Detail: $($test1_2.Content.detail)"

# Test 1.3: Reserved I2C Address (0x00)
Write-Host "`nTest 1.3: Reserved I2C address (0x00)" -ForegroundColor Yellow
$test1_3 = Invoke-TestRequest -Url "$apiBase/sensors/ESP_00000001/NULL" -Body @{
    sensor_type = "sht31_temp"
    interface_type = "I2C"
    i2c_address = 0
} -ExpectedStatus 400

$passed = ($test1_3.StatusCode -eq 400) -and ($test1_3.Content.detail -like "*reserved*" -or $test1_3.Content.detail -like "*0x00*")
Write-TestResult -TestName "1.3: Reserved I2C address (0x00)" -Passed $passed `
    -Expected "400 Bad Request: 'i2c_address 0x00 is reserved by I2C specification'" `
    -Actual "Status: $($test1_3.StatusCode), Detail: $($test1_3.Content.detail)"

# Test 1.4: Reserved I2C Address (0x7F)
Write-Host "`nTest 1.4: Reserved I2C address (0x7F)" -ForegroundColor Yellow
$test1_4 = Invoke-TestRequest -Url "$apiBase/sensors/ESP_00000001/NULL" -Body @{
    sensor_type = "sht31_temp"
    interface_type = "I2C"
    i2c_address = 127
} -ExpectedStatus 400

$passed = ($test1_4.StatusCode -eq 400) -and ($test1_4.Content.detail -like "*reserved*" -or $test1_4.Content.detail -like "*0x7F*")
Write-TestResult -TestName "1.4: Reserved I2C address (0x7F)" -Passed $passed `
    -Expected "400 Bad Request: 'i2c_address 0x7F is reserved by I2C specification'" `
    -Actual "Status: $($test1_4.StatusCode), Detail: $($test1_4.Content.detail)"

# Test 1.5: Valid I2C Address (0x44)
Write-Host "`nTest 1.5: Valid I2C address (0x44)" -ForegroundColor Yellow
$test1_5 = Invoke-TestRequest -Url "$apiBase/sensors/ESP_00000001/NULL" -Body @{
    sensor_type = "sht31_temp"
    sensor_name = "SHT31 Temperature"
    interface_type = "I2C"
    i2c_address = 68
} -ExpectedStatus 201

$passed = ($test1_5.StatusCode -eq 201)
Write-TestResult -TestName "1.5: Valid I2C address (0x44)" -Passed $passed `
    -Expected "201 Created" `
    -Actual "Status: $($test1_5.StatusCode)"

# =============================================================================
# Section 2.2: Fix #2 - Input-Only Pin Protection (3 Tests)
# =============================================================================
Write-Host "`n=== Section 2.2: Input-Only Pin Protection ===" -ForegroundColor Cyan

# Test 2.1: Actuator on Input-Only Pin (GPIO 34)
Write-Host "`nTest 2.1: Actuator on input-only pin (GPIO 34)" -ForegroundColor Yellow
$test2_1 = Invoke-TestRequest -Url "$apiBase/actuators/ESP_00000001/34" -Body @{
    actuator_type = "pump"
    actuator_name = "Water Pump"
    enabled = $true
} -ExpectedStatus 409

$passed = ($test2_1.StatusCode -eq 409) -and ($test2_1.Content.detail.message -like "*input-only*" -or $test2_1.Content.error -like "*GPIO_CONFLICT*")
Write-TestResult -TestName "2.1: Actuator on input-only pin" -Passed $passed `
    -Expected "409 Conflict: 'GPIO 34 is input-only and cannot be used for actuators'" `
    -Actual "Status: $($test2_1.StatusCode), Message: $($test2_1.Content.detail.message)"

# Test 2.2: Sensor on Input-Only Pin (OK!)
Write-Host "`nTest 2.2: Sensor on input-only pin (GPIO 34) - OK!" -ForegroundColor Yellow
$test2_2 = Invoke-TestRequest -Url "$apiBase/sensors/ESP_00000001/34" -Body @{
    sensor_type = "soil_moisture"
    sensor_name = "Soil Sensor"
    interface_type = "ANALOG"
    enabled = $true
} -ExpectedStatus 201

$passed = ($test2_2.StatusCode -eq 201)
Write-TestResult -TestName "2.2: Sensor on input-only pin (OK)" -Passed $passed `
    -Expected "201 Created" `
    -Actual "Status: $($test2_2.StatusCode)"

# Test 2.3: Actuator on normal pin (GPIO 32)
Write-Host "`nTest 2.3: Actuator on normal pin (GPIO 32)" -ForegroundColor Yellow
$test2_3 = Invoke-TestRequest -Url "$apiBase/actuators/ESP_00000001/32" -Body @{
    actuator_type = "pump"
    actuator_name = "Pump"
    enabled = $true
} -ExpectedStatus 201

$passed = ($test2_3.StatusCode -eq 201)
Write-TestResult -TestName "2.3: Actuator on normal pin" -Passed $passed `
    -Expected "201 Created" `
    -Actual "Status: $($test2_3.StatusCode)"

# =============================================================================
# Section 2.3: Fix #3 - I2C Pin Protection (3 Tests)
# =============================================================================
Write-Host "`n=== Section 2.3: I2C Pin Protection ===" -ForegroundColor Cyan

# Test 3.1: ANALOG on I2C Pin (GPIO 21)
Write-Host "`nTest 3.1: ANALOG sensor on I2C pin (GPIO 21)" -ForegroundColor Yellow
$test3_1 = Invoke-TestRequest -Url "$apiBase/sensors/ESP_00000001/21" -Body @{
    sensor_type = "soil_moisture"
    sensor_name = "Soil"
    interface_type = "ANALOG"
} -ExpectedStatus 409

$passed = ($test3_1.StatusCode -eq 409) -and ($test3_1.Content.detail.message -like "*I2C*" -or $test3_1.Content.detail.message -like "*reserved*")
Write-TestResult -TestName "3.1: ANALOG on I2C pin" -Passed $passed `
    -Expected "409 Conflict: 'GPIO 21 is reserved for I2C bus communication'" `
    -Actual "Status: $($test3_1.StatusCode), Message: $($test3_1.Content.detail.message)"

# Test 3.2: I2C Sensor (gpio=NULL) - OK!
Write-Host "`nTest 3.2: I2C sensor (gpio=NULL) - OK!" -ForegroundColor Yellow
$test3_2 = Invoke-TestRequest -Url "$apiBase/sensors/ESP_00000001/NULL" -Body @{
    sensor_type = "sht31_temp"
    sensor_name = "SHT31"
    interface_type = "I2C"
    i2c_address = 68
} -ExpectedStatus 201

$passed = ($test3_2.StatusCode -eq 201)
Write-TestResult -TestName "3.2: I2C sensor (OK)" -Passed $passed `
    -Expected "201 Created" `
    -Actual "Status: $($test3_2.StatusCode)"

# Test 3.3: ANALOG on normal pin (GPIO 32)
Write-Host "`nTest 3.3: ANALOG sensor on normal pin (GPIO 32)" -ForegroundColor Yellow
$test3_3 = Invoke-TestRequest -Url "$apiBase/sensors/ESP_00000001/32" -Body @{
    sensor_type = "soil_moisture"
    interface_type = "ANALOG"
} -ExpectedStatus 201

$passed = ($test3_3.StatusCode -eq 201)
Write-TestResult -TestName "3.3: ANALOG on normal pin" -Passed $passed `
    -Expected "201 Created" `
    -Actual "Status: $($test3_3.StatusCode)"

# =============================================================================
# Section 2.4: Fix #4 - ESP Model Awareness (6 Tests)
# =============================================================================
Write-Host "`n=== Section 2.4: ESP Model Awareness ===" -ForegroundColor Cyan

# Test 4.1: C3 - GPIO out of range (GPIO 34)
Write-Host "`nTest 4.1: C3 - GPIO out of range (GPIO 34)" -ForegroundColor Yellow
$test4_1 = Invoke-TestRequest -Url "$apiBase/sensors/ESP_C3_TEST/34" -Body @{
    sensor_type = "soil_moisture"
    interface_type = "ANALOG"
} -ExpectedStatus 409

$passed = ($test4_1.StatusCode -eq 409) -and ($test4_1.Content.detail.message -like "*out of range*" -or $test4_1.Content.detail.message -like "*0-21*")
Write-TestResult -TestName "4.1: C3 - GPIO out of range" -Passed $passed `
    -Expected "409 Conflict: 'GPIO 34 out of range for XIAO_ESP32_C3 (0-21)'" `
    -Actual "Status: $($test4_1.StatusCode), Message: $($test4_1.Content.detail.message)"

# Test 4.2: C3 - ANALOG on C3 I2C Pin (GPIO 4)
Write-Host "`nTest 4.2: C3 - ANALOG on C3 I2C pin (GPIO 4)" -ForegroundColor Yellow
$test4_2 = Invoke-TestRequest -Url "$apiBase/sensors/ESP_C3_TEST/4" -Body @{
    sensor_type = "soil_moisture"
    interface_type = "ANALOG"
} -ExpectedStatus 409

$passed = ($test4_2.StatusCode -eq 409) -and ($test4_2.Content.detail.message -like "*I2C*" -or $test4_2.Content.detail.message -like "*reserved*")
Write-TestResult -TestName "4.2: C3 - ANALOG on I2C pin" -Passed $passed `
    -Expected "409 Conflict: 'GPIO 4 is reserved for I2C bus' (C3 nutzt GPIO 4/5!)" `
    -Actual "Status: $($test4_2.StatusCode), Message: $($test4_2.Content.detail.message)"

# Test 4.3: C3 - I2C Sensor (OK!)
Write-Host "`nTest 4.3: C3 - I2C sensor (OK!)" -ForegroundColor Yellow
$test4_3 = Invoke-TestRequest -Url "$apiBase/sensors/ESP_C3_TEST/NULL" -Body @{
    sensor_type = "sht31_temp"
    interface_type = "I2C"
    i2c_address = 68
} -ExpectedStatus 201

$passed = ($test4_3.StatusCode -eq 201)
Write-TestResult -TestName "4.3: C3 - I2C sensor (OK)" -Passed $passed `
    -Expected "201 Created" `
    -Actual "Status: $($test4_3.StatusCode)"

# Test 4.4: WROOM - Actuator on GPIO 35 (Input-Only)
Write-Host "`nTest 4.4: WROOM - Actuator on GPIO 35 (Input-Only)" -ForegroundColor Yellow
$test4_4 = Invoke-TestRequest -Url "$apiBase/actuators/ESP_00000001/35" -Body @{
    actuator_type = "pump"
    actuator_name = "Pump"
} -ExpectedStatus 409

$passed = ($test4_4.StatusCode -eq 409) -and ($test4_4.Content.detail.message -like "*input-only*")
Write-TestResult -TestName "4.4: WROOM - Actuator on input-only" -Passed $passed `
    -Expected "409 Conflict (Input-Only auf WROOM!)" `
    -Actual "Status: $($test4_4.StatusCode), Message: $($test4_4.Content.detail.message)"

# Test 4.5: C3 - Actuator on GPIO 10 (OK! C3 hat keine Input-Only)
Write-Host "`nTest 4.5: C3 - Actuator on GPIO 10 (OK! C3 has no input-only)" -ForegroundColor Yellow
$test4_5 = Invoke-TestRequest -Url "$apiBase/actuators/ESP_C3_TEST/10" -Body @{
    actuator_type = "pump"
    actuator_name = "Pump"
} -ExpectedStatus 201

$passed = ($test4_5.StatusCode -eq 201)
Write-TestResult -TestName "4.5: C3 - Actuator on GPIO 10 (OK)" -Passed $passed `
    -Expected "201 Created" `
    -Actual "Status: $($test4_5.StatusCode)"

# Test 4.6: Unknown hardware_type - Default to WROOM
Write-Host "`nTest 4.6: Unknown hardware_type - Default to WROOM" -ForegroundColor Yellow
$test4_6 = Invoke-TestRequest -Url "$apiBase/sensors/ESP_UNKNOWN/21" -Body @{
    sensor_type = "soil_moisture"
    interface_type = "ANALOG"
} -ExpectedStatus 409

$passed = ($test4_6.StatusCode -eq 409) -and ($test4_6.Content.detail.message -like "*I2C*" -or $test4_6.Content.detail.message -like "*reserved*")
Write-TestResult -TestName "4.6: Unknown hardware_type defaults to WROOM" -Passed $passed `
    -Expected "409 Conflict (defaulted auf WROOM → GPIO 21 ist I2C!)" `
    -Actual "Status: $($test4_6.StatusCode), Message: $($test4_6.Content.detail.message)"

# =============================================================================
# Test Summary
# =============================================================================
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "Test Summary" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Total Tests: $($script:testResults.Count)" -ForegroundColor White
Write-Host "✅ Passed: $script:passed" -ForegroundColor Green
Write-Host "❌ Failed: $script:failed" -ForegroundColor Red
Write-Host "========================================" -ForegroundColor Cyan

if ($script:failed -eq 0) {
    Write-Host "`n🎉 ALL TESTS PASSED! Ready for production deployment." -ForegroundColor Green
    exit 0
} else {
    Write-Host "`n⚠️  Some tests failed. Review the details above." -ForegroundColor Yellow
    exit 1
}
