#include <unity.h>
#include "../src/drivers/pwm_controller.h"
#include "../src/drivers/gpio_manager.h"
#include "../src/utils/logger.h"

// ============================================
// PWM Controller Unit Tests
// ============================================
// Phase 3: Hardware Abstraction Layer Testing
//
// Test Strategy:
// - Basic initialization and lifecycle
// - Channel management (attach/detach)
// - Channel exhaustion handling
// - PWM output control (write/writePercent)
// - Frequency and resolution configuration
// - Error handling

// ============================================
// TEST SETUP & TEARDOWN
// ============================================

void setUp(void) {
    // Setup runs before each test
    static bool gpio_initialized = false;
    if (!gpio_initialized) {
        gpioManager.initializeAllPinsToSafeMode();
        gpio_initialized = true;
    }
}

void tearDown(void) {
    // Teardown runs after each test
    if (pwmController.isInitialized()) {
        pwmController.end();
    }
}

// ============================================
// BASIC INITIALIZATION TESTS
// ============================================

void test_pwm_controller_initialization(void) {
    // Test successful initialization
    bool result = pwmController.begin();
    TEST_ASSERT_TRUE_MESSAGE(result, "PWM Controller initialization should succeed");
    TEST_ASSERT_TRUE_MESSAGE(pwmController.isInitialized(), 
                            "PWM Controller should be marked as initialized");
}

void test_pwm_controller_double_initialization(void) {
    // First initialization
    bool result1 = pwmController.begin();
    TEST_ASSERT_TRUE_MESSAGE(result1, "First initialization should succeed");
    
    // Second initialization (should be safe)
    bool result2 = pwmController.begin();
    TEST_ASSERT_TRUE_MESSAGE(result2, "Double initialization should be safe");
    TEST_ASSERT_TRUE_MESSAGE(pwmController.isInitialized(), 
                            "PWM Controller should still be initialized");
}

void test_pwm_controller_end(void) {
    // Initialize
    pwmController.begin();
    TEST_ASSERT_TRUE(pwmController.isInitialized());
    
    // End
    pwmController.end();
    TEST_ASSERT_FALSE_MESSAGE(pwmController.isInitialized(), 
                             "PWM Controller should be deinitialized after end()");
}

// ============================================
// CHANNEL ATTACHMENT TESTS
// ============================================

void test_pwm_attach_channel_without_init(void) {
    // Try to attach without initialization
    uint8_t channel;
    bool result = pwmController.attachChannel(10, channel);
    TEST_ASSERT_FALSE_MESSAGE(result, 
                             "Channel attach should fail when not initialized");
}

void test_pwm_attach_channel_with_init(void) {
    // Initialize
    pwmController.begin();
    
    // Attach channel to GPIO 10 (safe pin on most boards)
    uint8_t channel;
    bool result = pwmController.attachChannel(10, channel);
    TEST_ASSERT_TRUE_MESSAGE(result, "Channel attach should succeed");
    TEST_ASSERT_TRUE_MESSAGE(pwmController.isChannelAttached(channel), 
                            "Channel should be marked as attached");
    
    // Verify channel assignment
    uint8_t found_channel = pwmController.getChannelForGPIO(10);
    TEST_ASSERT_EQUAL_MESSAGE(channel, found_channel, 
                             "GPIO should be mapped to correct channel");
}

void test_pwm_attach_same_gpio_twice(void) {
    // Initialize
    pwmController.begin();
    
    // Attach channel to GPIO 10
    uint8_t channel1;
    bool result1 = pwmController.attachChannel(10, channel1);
    TEST_ASSERT_TRUE(result1);
    
    // Try to attach same GPIO again (should return same channel)
    uint8_t channel2;
    bool result2 = pwmController.attachChannel(10, channel2);
    TEST_ASSERT_TRUE_MESSAGE(result2, "Re-attaching same GPIO should succeed");
    TEST_ASSERT_EQUAL_MESSAGE(channel1, channel2, 
                             "Should return same channel for same GPIO");
}

// ============================================
// CHANNEL DETACHMENT TESTS
// ============================================

void test_pwm_detach_channel_without_init(void) {
    // Try to detach without initialization
    bool result = pwmController.detachChannel(0);
    TEST_ASSERT_FALSE_MESSAGE(result, 
                             "Channel detach should fail when not initialized");
}

void test_pwm_detach_unattached_channel(void) {
    // Initialize
    pwmController.begin();
    
    // Try to detach unattached channel
    bool result = pwmController.detachChannel(0);
    TEST_ASSERT_FALSE_MESSAGE(result, 
                             "Detaching unattached channel should fail");
}

void test_pwm_detach_attached_channel(void) {
    // Initialize
    pwmController.begin();
    
    // Attach channel
    uint8_t channel;
    pwmController.attachChannel(10, channel);
    TEST_ASSERT_TRUE(pwmController.isChannelAttached(channel));
    
    // Detach channel
    bool result = pwmController.detachChannel(channel);
    TEST_ASSERT_TRUE_MESSAGE(result, "Detach should succeed");
    TEST_ASSERT_FALSE_MESSAGE(pwmController.isChannelAttached(channel), 
                             "Channel should no longer be attached");
}

// ============================================
// CHANNEL EXHAUSTION TESTS
// ============================================

void test_pwm_channel_exhaustion(void) {
    // Initialize
    pwmController.begin();
    
    // Get max channels (6 for XIAO, 16 for WROOM)
    uint8_t max_attempts = 20;  // Try more than max
    uint8_t successful_attachments = 0;
    uint8_t channels[20];
    
    // Try to attach channels until exhausted
    for (uint8_t gpio = 2; gpio < 22 && successful_attachments < max_attempts; gpio++) {
        // Skip I2C pins (already reserved)
        if (gpio == 4 || gpio == 5) continue;
        
        uint8_t channel;
        if (pwmController.attachChannel(gpio, channel)) {
            channels[successful_attachments] = channel;
            successful_attachments++;
        }
    }
    
    char msg[100];
    sprintf(msg, "Successfully attached %d PWM channels", successful_attachments);
    TEST_MESSAGE(msg);
    
    // Should have attached at least some channels
    TEST_ASSERT_TRUE_MESSAGE(successful_attachments > 0, 
                            "Should attach at least one channel");
    
    // Clean up
    for (uint8_t i = 0; i < successful_attachments; i++) {
        pwmController.detachChannel(channels[i]);
    }
}

// ============================================
// PWM OUTPUT TESTS (ABSOLUTE DUTY CYCLE)
// ============================================

void test_pwm_write_without_init(void) {
    // Try to write without initialization
    bool result = pwmController.write(0, 2048);
    TEST_ASSERT_FALSE_MESSAGE(result, 
                             "Write should fail when not initialized");
}

void test_pwm_write_unattached_channel(void) {
    // Initialize
    pwmController.begin();
    
    // Try to write to unattached channel
    bool result = pwmController.write(0, 2048);
    TEST_ASSERT_FALSE_MESSAGE(result, 
                             "Write should fail for unattached channel");
}

void test_pwm_write_valid_duty(void) {
    // Initialize
    pwmController.begin();
    
    // Attach channel
    uint8_t channel;
    pwmController.attachChannel(10, channel);
    
    // Write valid duty cycle (mid-range for 12-bit: 2048/4095)
    bool result = pwmController.write(channel, 2048);
    TEST_ASSERT_TRUE_MESSAGE(result, "Write should succeed with valid duty");
}

void test_pwm_write_out_of_range(void) {
    // Initialize
    pwmController.begin();
    
    // Attach channel
    uint8_t channel;
    pwmController.attachChannel(10, channel);
    
    // Try to write duty cycle exceeding max (4095 for 12-bit)
    bool result = pwmController.write(channel, 5000);
    TEST_ASSERT_FALSE_MESSAGE(result, 
                             "Write should fail with out-of-range duty");
}

// ============================================
// PWM OUTPUT TESTS (PERCENTAGE DUTY CYCLE)
// ============================================

void test_pwm_write_percent_without_init(void) {
    // Try to write without initialization
    bool result = pwmController.writePercent(0, 50.0);
    TEST_ASSERT_FALSE_MESSAGE(result, 
                             "WritePercent should fail when not initialized");
}

void test_pwm_write_percent_valid(void) {
    // Initialize
    pwmController.begin();
    
    // Attach channel
    uint8_t channel;
    pwmController.attachChannel(10, channel);
    
    // Write valid percentages
    TEST_ASSERT_TRUE(pwmController.writePercent(channel, 0.0));
    TEST_ASSERT_TRUE(pwmController.writePercent(channel, 50.0));
    TEST_ASSERT_TRUE(pwmController.writePercent(channel, 100.0));
}

void test_pwm_write_percent_out_of_range(void) {
    // Initialize
    pwmController.begin();
    
    // Attach channel
    uint8_t channel;
    pwmController.attachChannel(10, channel);
    
    // Try invalid percentages
    TEST_ASSERT_FALSE_MESSAGE(pwmController.writePercent(channel, -10.0),
                             "Negative percentage should fail");
    TEST_ASSERT_FALSE_MESSAGE(pwmController.writePercent(channel, 150.0),
                             "Percentage > 100 should fail");
}

// ============================================
// FREQUENCY CONFIGURATION TESTS
// ============================================

void test_pwm_set_frequency_without_init(void) {
    // Try to set frequency without initialization
    bool result = pwmController.setFrequency(0, 5000);
    TEST_ASSERT_FALSE_MESSAGE(result, 
                             "SetFrequency should fail when not initialized");
}

void test_pwm_set_frequency_valid(void) {
    // Initialize
    pwmController.begin();
    
    // Attach channel
    uint8_t channel;
    pwmController.attachChannel(10, channel);
    
    // Set valid frequency (5 kHz)
    bool result = pwmController.setFrequency(channel, 5000);
    TEST_ASSERT_TRUE_MESSAGE(result, "SetFrequency should succeed");
}

void test_pwm_set_frequency_invalid(void) {
    // Initialize
    pwmController.begin();
    
    // Attach channel
    uint8_t channel;
    pwmController.attachChannel(10, channel);
    
    // Try invalid frequencies
    TEST_ASSERT_FALSE_MESSAGE(pwmController.setFrequency(channel, 0),
                             "Zero frequency should fail");
    TEST_ASSERT_FALSE_MESSAGE(pwmController.setFrequency(channel, 50000000),
                             "Frequency > 40MHz should fail");
}

// ============================================
// RESOLUTION CONFIGURATION TESTS
// ============================================

void test_pwm_set_resolution_without_init(void) {
    // Try to set resolution without initialization
    bool result = pwmController.setResolution(0, 10);
    TEST_ASSERT_FALSE_MESSAGE(result, 
                             "SetResolution should fail when not initialized");
}

void test_pwm_set_resolution_valid(void) {
    // Initialize
    pwmController.begin();
    
    // Attach channel
    uint8_t channel;
    pwmController.attachChannel(10, channel);
    
    // Set valid resolution (10-bit)
    bool result = pwmController.setResolution(channel, 10);
    TEST_ASSERT_TRUE_MESSAGE(result, "SetResolution should succeed");
}

void test_pwm_set_resolution_invalid(void) {
    // Initialize
    pwmController.begin();
    
    // Attach channel
    uint8_t channel;
    pwmController.attachChannel(10, channel);
    
    // Try invalid resolutions
    TEST_ASSERT_FALSE_MESSAGE(pwmController.setResolution(channel, 0),
                             "Zero resolution should fail");
    TEST_ASSERT_FALSE_MESSAGE(pwmController.setResolution(channel, 20),
                             "Resolution > 16 should fail");
}

// ============================================
// STATUS QUERY TESTS
// ============================================

void test_pwm_channel_status(void) {
    // Initialize
    pwmController.begin();
    
    // Get status
    String status = pwmController.getChannelStatus();
    TEST_ASSERT_TRUE_MESSAGE(status.length() > 0, 
                            "Status string should not be empty");
    TEST_ASSERT_TRUE_MESSAGE(status.indexOf("PWM Controller") >= 0, 
                            "Status should contain controller identifier");
}

// ============================================
// TEST RUNNER
// ============================================

void setup() {
    delay(2000);  // Wait for Serial
    
    UNITY_BEGIN();
    
    // Initialization Tests
    RUN_TEST(test_pwm_controller_initialization);
    RUN_TEST(test_pwm_controller_double_initialization);
    RUN_TEST(test_pwm_controller_end);
    
    // Channel Attachment Tests
    RUN_TEST(test_pwm_attach_channel_without_init);
    RUN_TEST(test_pwm_attach_channel_with_init);
    RUN_TEST(test_pwm_attach_same_gpio_twice);
    
    // Channel Detachment Tests
    RUN_TEST(test_pwm_detach_channel_without_init);
    RUN_TEST(test_pwm_detach_unattached_channel);
    RUN_TEST(test_pwm_detach_attached_channel);
    
    // Channel Exhaustion Tests
    RUN_TEST(test_pwm_channel_exhaustion);
    
    // PWM Output Tests (Absolute)
    RUN_TEST(test_pwm_write_without_init);
    RUN_TEST(test_pwm_write_unattached_channel);
    RUN_TEST(test_pwm_write_valid_duty);
    RUN_TEST(test_pwm_write_out_of_range);
    
    // PWM Output Tests (Percentage)
    RUN_TEST(test_pwm_write_percent_without_init);
    RUN_TEST(test_pwm_write_percent_valid);
    RUN_TEST(test_pwm_write_percent_out_of_range);
    
    // Frequency Configuration Tests
    RUN_TEST(test_pwm_set_frequency_without_init);
    RUN_TEST(test_pwm_set_frequency_valid);
    RUN_TEST(test_pwm_set_frequency_invalid);
    
    // Resolution Configuration Tests
    RUN_TEST(test_pwm_set_resolution_without_init);
    RUN_TEST(test_pwm_set_resolution_valid);
    RUN_TEST(test_pwm_set_resolution_invalid);
    
    // Status Tests
    RUN_TEST(test_pwm_channel_status);
    
    UNITY_END();
}

void loop() {
    // Tests run once in setup()
}

