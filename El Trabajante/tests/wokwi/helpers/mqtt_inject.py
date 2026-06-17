#!/usr/bin/env python3
"""
MQTT Message Injection Helper for Wokwi Tests

Usage:
    python mqtt_inject.py --host localhost --topic "kaiser/god/esp/ESP_SIM/actuator/5/command" \
                          --payload '{"command":"ON","value":1.0}'

    python mqtt_inject.py --host localhost --topic "kaiser/god/esp/ESP_SIM/zone/assign" \
                          --payload '{"zone_id":"test_zone","master_zone_id":"master","zone_name":"Test Zone","kaiser_id":"god"}'

    python mqtt_inject.py --host localhost --topic "kaiser/broadcast/emergency" \
                          --payload '{"auth_token":"master_token"}'
"""

import argparse
import json
import os
import time
import sys

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("Error: paho-mqtt not installed. Run: pip install paho-mqtt")
    sys.exit(1)


def on_connect(client, userdata, flags, rc):
    """Callback when connected to broker."""
    if rc == 0:
        print(f"Connected to MQTT broker")
    else:
        print(f"Connection failed with code {rc}")
        sys.exit(1)


def on_publish(client, userdata, mid):
    """Callback when message is published."""
    print(f"Message published (mid: {mid})")


def main():
    parser = argparse.ArgumentParser(
        description='MQTT Message Injection for Wokwi Tests',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Send actuator command
    python mqtt_inject.py --topic "kaiser/god/esp/ESP_SIM/actuator/5/command" \\
                          --payload '{"command":"ON","value":1.0}'

    # Send zone assignment
    python mqtt_inject.py --topic "kaiser/god/esp/ESP_SIM/zone/assign" \\
                          --payload '{"zone_id":"test","master_zone_id":"master","zone_name":"Test","kaiser_id":"god"}'

    # Send emergency stop
    python mqtt_inject.py --topic "kaiser/broadcast/emergency" \\
                          --payload '{"auth_token":"master_token"}'
        """
    )
    parser.add_argument('--host', default='localhost', help='MQTT broker host (default: localhost)')
    parser.add_argument('--port', type=int, default=1883, help='MQTT broker port (default: 1883)')
    parser.add_argument('--topic', required=True, help='MQTT topic to publish to')
    parser.add_argument('--payload', required=True, help='JSON payload to send')
    parser.add_argument('--delay', type=float, default=0, help='Delay before publish in seconds')
    parser.add_argument('--repeat', type=int, default=1, help='Number of times to publish')
    parser.add_argument('--interval', type=float, default=1.0, help='Interval between repeats in seconds')
    parser.add_argument('--qos', type=int, default=1, choices=[0, 1, 2], help='QoS level (default: 1)')
    parser.add_argument('--validate-json', action='store_true', help='Validate payload is valid JSON')
    parser.add_argument('--username', default=os.environ.get('MQTT_USERNAME', ''), help='MQTT username (or set MQTT_USERNAME env var)')
    parser.add_argument('--password', default=os.environ.get('MQTT_PASSWORD', ''), help='MQTT password (or set MQTT_PASSWORD env var)')

    args = parser.parse_args()

    # Validate JSON if requested
    if args.validate_json:
        try:
            json.loads(args.payload)
            print("Payload is valid JSON")
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON payload: {e}")
            sys.exit(1)

    # Apply delay
    if args.delay > 0:
        print(f"Waiting {args.delay}s before publishing...")
        time.sleep(args.delay)

    # Connect to broker
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_publish = on_publish

    if args.username:
        client.username_pw_set(args.username, args.password)

    try:
        print(f"Connecting to {args.host}:{args.port}...")
        client.connect(args.host, args.port, 60)
        client.loop_start()
        time.sleep(0.5)  # Wait for connection

        # Publish message(s)
        for i in range(args.repeat):
            print(f"[{i+1}/{args.repeat}] Publishing to {args.topic}")
            print(f"  Payload: {args.payload}")
            result = client.publish(args.topic, args.payload, qos=args.qos)
            result.wait_for_publish()

            if i < args.repeat - 1:
                time.sleep(args.interval)

        client.loop_stop()
        client.disconnect()
        print("Done!")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
