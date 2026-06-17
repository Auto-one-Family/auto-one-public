"""
MQTT Connection Test Script

Tests MQTT broker connectivity and authentication.
Helps diagnose connection issues.
"""

import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import paho.mqtt.client as mqtt
from src.core.config import get_settings


def test_connection(username=None, password=None):
    """Test MQTT connection with given credentials."""
    settings = get_settings()
    
    broker = settings.mqtt.broker_host
    port = settings.mqtt.broker_port
    
    print(f"\n{'='*60}")
    print(f"Testing MQTT Connection")
    print(f"{'='*60}")
    print(f"Broker: {broker}:{port}")
    print(f"Username: {username or '(none)'}")
    print(f"Password: {'***' if password else '(none)'}")
    print(f"{'='*60}\n")
    
    connected = False
    connection_result = None
    
    def on_connect(client, userdata, flags, rc):
        nonlocal connected, connection_result
        connection_result = rc
        
        error_messages = {
            0: "[OK] Connection successful",
            1: "[FAIL] Connection refused - incorrect protocol version",
            2: "[FAIL] Connection refused - invalid client identifier",
            3: "[FAIL] Connection refused - server unavailable",
            4: "[FAIL] Connection refused - bad username or password",
            5: "[FAIL] Connection refused - not authorized",
        }
        
        msg = error_messages.get(rc, f"✗ Unknown error code: {rc}")
        print(f"Connection result: {msg}")
        
        if rc == 0:
            connected = True
        
    def on_disconnect(client, userdata, rc):
        if rc != 0:
            print(f"[WARN] Unexpected disconnect (code: {rc})")
    
    # Create client
    client = mqtt.Client(
        client_id=f"mqtt_test_{int(time.time())}",
        clean_session=True,
        protocol=mqtt.MQTTv311,
    )
    
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    
    # Set credentials if provided
    if username and password:
        client.username_pw_set(username, password)
    
    try:
        # Connect
        client.connect(broker, port, keepalive=60)
        client.loop_start()
        
        # Wait for connection
        timeout = 5
        start = time.time()
        while connection_result is None and (time.time() - start) < timeout:
            time.sleep(0.1)
        
        if connection_result is None:
            print("[FAIL] Connection timeout (broker not responding)")
            return False
        
        # If connected, try to publish
        if connected:
            print("\nTesting publish...")
            result = client.publish("test/connection", "test_message", qos=1)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                print("[OK] Publish successful")
            else:
                print(f"[FAIL] Publish failed: {result.rc}")
            
            time.sleep(1)
        
        client.loop_stop()
        client.disconnect()
        
        return connected
        
    except Exception as e:
        print(f"[FAIL] Connection error: {e}")
        return False


def check_env_file():
    """Check if .env file exists and has MQTT credentials."""
    env_path = Path(__file__).parent.parent / ".env"
    
    print(f"\n{'='*60}")
    print(f"Checking .env File")
    print(f"{'='*60}")
    print(f"Path: {env_path}")
    
    if env_path.exists():
        print("[OK] .env file exists")
        
        with open(env_path, 'r') as f:
            content = f.read()
        
        # Check for MQTT settings
        mqtt_vars = [
            "MQTT_BROKER_HOST",
            "MQTT_BROKER_PORT",
            "MQTT_USERNAME",
            "MQTT_PASSWORD",
        ]
        
        print("\nMQTT Environment Variables:")
        for var in mqtt_vars:
            if var in content:
                # Show value but mask password
                line = [ln for ln in content.split('\n') if ln.startswith(var)]
                if line:
                    value = line[0].split('=', 1)[1] if '=' in line[0] else ''
                    if 'PASSWORD' in var and value:
                        value = "***"
                    print(f"  {var} = {value or '(empty)'}")
            else:
                print(f"  {var} = (not set)")
    else:
        print("[FAIL] .env file not found")
        print("\nCreate a .env file with:")
        print("  MQTT_BROKER_HOST=localhost")
        print("  MQTT_BROKER_PORT=1883")
        print("  MQTT_USERNAME=your_username")
        print("  MQTT_PASSWORD=your_password")
    
    print(f"{'='*60}\n")


def check_mosquitto():
    """Check Mosquitto broker status and configuration."""
    print(f"\n{'='*60}")
    print(f"Checking Mosquitto Broker")
    print(f"{'='*60}")
    
    # Common Mosquitto config locations on Windows
    config_paths = [
        Path("C:/Program Files/mosquitto/mosquitto.conf"),
        Path("C:/Program Files (x86)/mosquitto/mosquitto.conf"),
        Path("C:/mosquitto/mosquitto.conf"),
    ]
    
    found_config = False
    for config_path in config_paths:
        if config_path.exists():
            print(f"[OK] Config found: {config_path}")
            found_config = True
            
            # Read and check for auth settings
            try:
                with open(config_path, 'r') as f:
                    content = f.read()
                
                print("\nAuth-related settings:")
                for line in content.split('\n'):
                    line = line.strip()
                    if line and not line.startswith('#'):
                        if any(keyword in line for keyword in ['allow_anonymous', 'password_file', 'acl_file']):
                            print(f"  {line}")
            except Exception as e:
                print(f"  Could not read config: {e}")
            
            break
    
    if not found_config:
        print("[FAIL] Mosquitto config not found at common locations")
        print("  Check: C:/Program Files/mosquitto/")
    
    print(f"{'='*60}\n")


def main():
    """Main test function."""
    print("\n" + "="*60)
    print("MQTT DIAGNOSTICS TOOL")
    print("="*60)
    
    # Step 1: Check .env file
    check_env_file()
    
    # Step 2: Check Mosquitto
    check_mosquitto()
    
    # Step 3: Load settings
    settings = get_settings()
    
    # Step 4: Test connection without auth
    print("\n[TEST 1] Testing connection WITHOUT authentication...")
    result1 = test_connection()
    
    # Step 5: Test connection with auth from settings
    if settings.mqtt.username and settings.mqtt.password:
        print("\n[TEST 2] Testing connection WITH authentication (from .env)...")
        result2 = test_connection(
            username=settings.mqtt.username,
            password=settings.mqtt.password
        )
    else:
        print("\n[TEST 2] Skipped - No credentials in settings")
        result2 = False
    
    # Step 6: Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    
    if result1:
        print("[OK] Broker allows anonymous connections")
    elif result2:
        print("[OK] Authentication required and working")
    else:
        print("[FAIL] Connection failed")
        print("\nPossible solutions:")
        print("  1. Check if Mosquitto broker is running:")
        print("     - Windows Services: Look for 'Mosquitto Broker'")
        print("     - Or run: net start mosquitto")
        print()
        print("  2. If broker requires auth, add to .env:")
        print("     MQTT_USERNAME=your_username")
        print("     MQTT_PASSWORD=your_password")
        print()
        print("  3. Configure Mosquitto to allow anonymous:")
        print("     Edit mosquitto.conf:")
        print("     allow_anonymous true")
        print("     listener 1883")
        print()
        print("  4. Or create password file:")
        print("     mosquitto_passwd -c passwordfile username")
        print("     Then in mosquitto.conf:")
        print("     password_file /path/to/passwordfile")
    
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()