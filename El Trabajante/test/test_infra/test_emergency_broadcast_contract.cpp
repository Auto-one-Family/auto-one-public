#include <unity.h>

#ifdef NATIVE_TEST
    #include "../mocks/Arduino.h"
#else
    #include <Arduino.h>
#endif

#include "tasks/emergency_broadcast_contract.h"

void setUp(void) {}
void tearDown(void) {}

static BroadcastEmergencyContractInput baseInput() {
    BroadcastEmergencyContractInput input{};
    input.command_present = true;
    input.command_is_string = true;
    input.command_value = "stop_all";
    input.action_present = false;
    input.action_is_string = false;
    input.action_value = nullptr;
    input.auth_token_present = false;
    input.auth_token_is_string = false;
    input.reason_present = false;
    input.reason_is_string = false;
    input.issued_by_present = false;
    input.issued_by_is_string = false;
    input.timestamp_present = false;
    input.timestamp_is_string = false;
    return input;
}

void test_broadcast_contract_accepts_valid_command() {
    BroadcastEmergencyContractInput input = baseInput();
    BroadcastEmergencyContractResult result = validateBroadcastEmergencyContract(input);

    TEST_ASSERT_EQUAL_UINT8(static_cast<uint8_t>(BroadcastEmergencyContractStatus::VALID),
                            static_cast<uint8_t>(result.status));
    TEST_ASSERT_EQUAL_STRING("NONE", result.reject_code);
    TEST_ASSERT_EQUAL_STRING("stop_all", result.normalized_command);
}

void test_broadcast_contract_accepts_legacy_action_alias() {
    BroadcastEmergencyContractInput input = baseInput();
    input.command_present = false;
    input.command_is_string = false;
    input.command_value = nullptr;
    input.action_present = true;
    input.action_is_string = true;
    input.action_value = "emergency_stop";

    BroadcastEmergencyContractResult result = validateBroadcastEmergencyContract(input);
    TEST_ASSERT_EQUAL_UINT8(static_cast<uint8_t>(BroadcastEmergencyContractStatus::VALID),
                            static_cast<uint8_t>(result.status));
    TEST_ASSERT_EQUAL_STRING("emergency_stop", result.normalized_command);
}

void test_broadcast_contract_rejects_missing_command_fields() {
    BroadcastEmergencyContractInput input = baseInput();
    input.command_present = false;
    input.command_is_string = false;
    input.command_value = nullptr;

    BroadcastEmergencyContractResult result = validateBroadcastEmergencyContract(input);
    TEST_ASSERT_EQUAL_UINT8(static_cast<uint8_t>(BroadcastEmergencyContractStatus::CONTRACT_MISMATCH),
                            static_cast<uint8_t>(result.status));
    TEST_ASSERT_EQUAL_STRING("EMERGENCY_CONTRACT_MISMATCH", result.reject_code);
    TEST_ASSERT_EQUAL_STRING("MISSING_COMMAND_FIELD", result.detail_code);
}

void test_broadcast_contract_rejects_wrong_command_type() {
    BroadcastEmergencyContractInput input = baseInput();
    input.command_is_string = false;

    BroadcastEmergencyContractResult result = validateBroadcastEmergencyContract(input);
    TEST_ASSERT_EQUAL_STRING("FIELD_TYPE_COMMAND", result.detail_code);
}

void test_broadcast_contract_rejects_unknown_command_value() {
    BroadcastEmergencyContractInput input = baseInput();
    input.command_value = "pause_all";

    BroadcastEmergencyContractResult result = validateBroadcastEmergencyContract(input);
    TEST_ASSERT_EQUAL_STRING("UNKNOWN_COMMAND_VALUE", result.detail_code);
}

void test_broadcast_contract_rejects_conflicting_command_and_action() {
    BroadcastEmergencyContractInput input = baseInput();
    input.action_present = true;
    input.action_is_string = true;
    input.action_value = "emergency_stop";

    BroadcastEmergencyContractResult result = validateBroadcastEmergencyContract(input);
    TEST_ASSERT_EQUAL_STRING("CONFLICTING_COMMAND_FIELDS", result.detail_code);
}

void test_broadcast_contract_rejects_partial_payload_with_wrong_optional_type() {
    BroadcastEmergencyContractInput input = baseInput();
    input.reason_present = true;
    input.reason_is_string = false;

    BroadcastEmergencyContractResult result = validateBroadcastEmergencyContract(input);
    TEST_ASSERT_EQUAL_STRING("FIELD_TYPE_REASON", result.detail_code);
}

#ifdef NATIVE_TEST
int main(int argc, char** argv) {
    (void)argc;
    (void)argv;
#else
void setup() {
    delay(2000);
#endif
    UNITY_BEGIN();
    RUN_TEST(test_broadcast_contract_accepts_valid_command);
    RUN_TEST(test_broadcast_contract_accepts_legacy_action_alias);
    RUN_TEST(test_broadcast_contract_rejects_missing_command_fields);
    RUN_TEST(test_broadcast_contract_rejects_wrong_command_type);
    RUN_TEST(test_broadcast_contract_rejects_unknown_command_value);
    RUN_TEST(test_broadcast_contract_rejects_conflicting_command_and_action);
    RUN_TEST(test_broadcast_contract_rejects_partial_payload_with_wrong_optional_type);
    UNITY_END();
#ifdef NATIVE_TEST
    return 0;
#endif
}

#ifndef NATIVE_TEST
void loop() {}
#endif
