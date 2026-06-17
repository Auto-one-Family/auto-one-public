#!/usr/bin/env python3
"""
Interactive ESP32 Testing Tool

Simuliert einen virtuellen ESP32, der mit dem LAUFENDEN Server kommuniziert.
Perfekt für Live-Testing und schrittweises Feature-Testing.

Usage:
    Terminal 1: python -m uvicorn src.main:app --reload
    Terminal 2: python interactive_test_esp32.py
"""

import sys
import time
import requests
import json
from pathlib import Path
from typing import Dict, Any

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from tests.esp32.mocks.mock_esp32_client import MockESP32Client


class InteractiveESP32Tester:
    """Interactive testing tool for ESP32 simulation against live server."""
    
    def __init__(self, server_url: str = "http://localhost:8000"):
        self.server_url = server_url
        self.mock_esp = None
        self.esp_id = "interactive-esp-001"
        
    def check_server(self) -> bool:
        """Check if server is running."""
        try:
            response = requests.get(f"{self.server_url}/health", timeout=2)
            if response.status_code == 200:
                print(f"✅ Server is running at {self.server_url}")
                return True
        except requests.exceptions.RequestException:
            pass
        
        print(f"❌ Server not reachable at {self.server_url}")
        print("\n⚠️  Please start server first:")
        print("    Terminal 1: cd 'El Servador/god_kaiser_server'")
        print("    Terminal 1: python -m uvicorn src.main:app --reload")
        return False
    
    def setup_esp32(self):
        """Initialize mock ESP32."""
        self.mock_esp = MockESP32Client(
            esp_id=self.esp_id,
            kaiser_id="test-kaiser-001"
        )
        print(f"\n✅ Virtual ESP32 initialized: {self.esp_id}")
        print(f"   Topics: kaiser/god/esp/{self.esp_id}/*")
    
    def add_sensor(self, gpio: int, sensor_type: str, raw_value: float):
        """Add a sensor to the virtual ESP32."""
        self.mock_esp.set_sensor_value(
            gpio=gpio,
            raw_value=raw_value,
            sensor_type=sensor_type
        )
        print(f"\n✅ Sensor added:")
        print(f"   GPIO: {gpio}")
        print(f"   Type: {sensor_type}")
        print(f"   Raw Value: {raw_value}")
    
    def read_sensor(self, gpio: int) -> Dict[str, Any]:
        """Read sensor value."""
        response = self.mock_esp.handle_command("sensor_read", {"gpio": gpio})
        
        print(f"\n📡 Sensor Reading (GPIO {gpio}):")
        print(f"   Status: {response['status']}")
        
        if response['status'] == 'ok':
            data = response['data']
            print(f"   Type: {data['type']}")
            print(f"   Raw Value: {data['raw_value']}")
            print(f"   Processed: {data.get('processed_value', 'N/A')}")
            print(f"   Timestamp: {data['timestamp']}")
            
            # Check published MQTT messages
            messages = self.mock_esp.get_published_messages()
            if messages:
                last_msg = messages[-1]
                print(f"\n📤 MQTT Published:")
                print(f"   Topic: {last_msg['topic']}")
                print(f"   Payload: {json.dumps(last_msg['payload'], indent=2)}")
        else:
            print(f"   Error: {response.get('error')}")
        
        return response
    
    def set_actuator(self, gpio: int, value: float, mode: str = "digital"):
        """Control actuator."""
        response = self.mock_esp.handle_command("actuator_set", {
            "gpio": gpio,
            "value": value,
            "mode": mode
        })
        
        print(f"\n🔧 Actuator Control (GPIO {gpio}):")
        print(f"   Status: {response['status']}")
        
        if response['status'] == 'ok':
            print(f"   Mode: {mode}")
            print(f"   Value: {value}")
            print(f"   State: {response['state']}")
            if mode == "pwm":
                print(f"   PWM Value: {response['pwm_value']}")
            
            # Check published MQTT messages
            messages = self.mock_esp.get_published_messages()
            if messages:
                last_msg = messages[-1]
                print(f"\n📤 MQTT Published:")
                print(f"   Topic: {last_msg['topic']}")
                print(f"   Payload: {json.dumps(last_msg['payload'], indent=2)}")
        else:
            print(f"   Error: {response.get('error')}")
        
        return response
    
    def send_heartbeat(self):
        """Send system heartbeat."""
        # Mock heartbeat (MockESP32Client doesn't have this yet)
        print(f"\n💓 Heartbeat sent from {self.esp_id}")
        print(f"   Topic: kaiser/god/esp/{self.esp_id}/system/heartbeat")
        print(f"   Status: online")
    
    def show_published_messages(self):
        """Show all published MQTT messages."""
        messages = self.mock_esp.get_published_messages()
        
        print(f"\n📊 Published Messages ({len(messages)} total):")
        for i, msg in enumerate(messages, 1):
            print(f"\n  [{i}] Topic: {msg['topic']}")
            print(f"      Payload: {json.dumps(msg['payload'], indent=8)}")
    
    def interactive_menu(self):
        """Interactive menu for testing."""
        while True:
            print("\n" + "="*60)
            print("🧪 INTERACTIVE ESP32 TESTING")
            print("="*60)
            print("\n1. Add Temperature Sensor (GPIO 34)")
            print("2. Add Moisture Sensor (GPIO 35)")
            print("3. Read Sensor")
            print("4. Control Actuator (GPIO 5 - Pump)")
            print("5. Send Heartbeat")
            print("6. Show All Published Messages")
            print("7. Clear Messages")
            print("0. Exit")
            
            choice = input("\nSelect option: ").strip()
            
            if choice == "1":
                self.add_sensor(gpio=34, sensor_type="DS18B20", raw_value=2150.0)
                time.sleep(0.5)
                self.read_sensor(gpio=34)
                
            elif choice == "2":
                self.add_sensor(gpio=35, sensor_type="analog", raw_value=2048.0)
                time.sleep(0.5)
                self.read_sensor(gpio=35)
                
            elif choice == "3":
                gpio = input("Enter GPIO number: ").strip()
                try:
                    self.read_sensor(int(gpio))
                except ValueError:
                    print("❌ Invalid GPIO number")
                    
            elif choice == "4":
                try:
                    value = input("Enter value (0=OFF, 1=ON): ").strip()
                    self.set_actuator(gpio=5, value=float(value), mode="digital")
                except ValueError:
                    print("❌ Invalid value")
                    
            elif choice == "5":
                self.send_heartbeat()
                
            elif choice == "6":
                self.show_published_messages()
                
            elif choice == "7":
                self.mock_esp.clear_published_messages()
                print("✅ Messages cleared")
                
            elif choice == "0":
                print("\n👋 Goodbye!")
                break
                
            else:
                print("❌ Invalid option")
    
    def run_demo(self):
        """Run automated demo scenario."""
        print("\n" + "="*60)
        print("🎬 RUNNING AUTOMATED DEMO")
        print("="*60)
        
        # Step 1: Add sensors
        print("\n📌 Step 1: Adding sensors...")
        self.add_sensor(gpio=34, sensor_type="DS18B20", raw_value=2150.0)
        time.sleep(1)
        self.add_sensor(gpio=35, sensor_type="analog", raw_value=2048.0)
        time.sleep(1)
        
        # Step 2: Read sensors
        print("\n📌 Step 2: Reading sensors...")
        self.read_sensor(gpio=34)
        time.sleep(1)
        self.read_sensor(gpio=35)
        time.sleep(1)
        
        # Step 3: Control actuator
        print("\n📌 Step 3: Controlling actuator...")
        self.set_actuator(gpio=5, value=1, mode="digital")
        time.sleep(2)
        self.set_actuator(gpio=5, value=0, mode="digital")
        time.sleep(1)
        
        # Step 4: PWM actuator
        print("\n📌 Step 4: PWM control...")
        self.set_actuator(gpio=7, value=0.75, mode="pwm")
        time.sleep(1)
        
        # Step 5: Show summary
        print("\n📌 Step 5: Message summary...")
        self.show_published_messages()
        
        print("\n✅ Demo completed!")


def main():
    """Main entry point."""
    tester = InteractiveESP32Tester()
    
    # Check if server is running
    if not tester.check_server():
        return 1
    
    # Setup virtual ESP32
    tester.setup_esp32()
    
    # Ask mode
    print("\n" + "="*60)
    print("Select Mode:")
    print("="*60)
    print("1. Interactive Menu (manual testing)")
    print("2. Automated Demo (quick overview)")
    
    mode = input("\nSelect mode (1 or 2): ").strip()
    
    if mode == "1":
        tester.interactive_menu()
    elif mode == "2":
        tester.run_demo()
    else:
        print("❌ Invalid mode")
        return 1
    
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n👋 Interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

























