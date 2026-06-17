#!/usr/bin/env python3
"""
AUT-539 Phase-D Verify — TCP-RST Reconnect Stress Test (paho-mqtt 2.x)
Simulates ESP32 MQTT disconnect via SO_LINGER (l_linger=0 → TCP RST on close).
Measures reconnect latency and success rate over N cycles.

Usage:
    python mqtt_rst_test.py [--cycles N] [--keepalive S]
"""
import argparse
import socket
import struct
import sys
import time
import threading
import platform

import paho.mqtt.client as mqtt

BROKER = "localhost"
PORT = 1883
CLIENT_ID = "ESP_EA5484_MOCK"
RECONNECT_TIMEOUT_S = 120


def linger_pack_rst() -> bytes:
    # Windows: struct linger { u_short l_onoff; u_short l_linger; } = 4 bytes
    # Linux:   struct linger { int l_onoff;     int l_linger;     } = 8 bytes
    if platform.system() == "Windows":
        return struct.pack("HH", 1, 0)
    return struct.pack("ii", 1, 0)


def run_cycle(cycle_num: int, keepalive: int) -> dict:
    print(f"\n--- Cycle {cycle_num:02d} ---")

    connected = threading.Event()
    disconnected = threading.Event()
    connect_ts = [None]
    first_reconnect_ts = [None]

    def on_connect(client, userdata, flags, reason_code, properties):
        ts = time.time()
        session_present = getattr(flags, "session_present", 0) if hasattr(flags, "session_present") else flags.get("session present", 0) if isinstance(flags, dict) else 0
        print(f"  on_connect rc={reason_code} session_present={session_present}")
        if connect_ts[0] is None:
            connect_ts[0] = ts
            connected.set()
        else:
            # This is a reconnect
            if first_reconnect_ts[0] is None:
                first_reconnect_ts[0] = ts

    def on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
        print(f"  on_disconnect rc={reason_code}")
        disconnected.set()

    try:
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=CLIENT_ID,
            clean_session=False,
            protocol=mqtt.MQTTv311,
        )
    except AttributeError:
        # Fallback for older paho
        client = mqtt.Client(
            client_id=CLIENT_ID,
            clean_session=False,
            protocol=mqtt.MQTTv311,
        )

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    t_start = time.time()
    try:
        client.connect(BROKER, PORT, keepalive=keepalive)
    except Exception as e:
        print(f"  [ERROR] connect failed: {e}")
        return {"cycle": cycle_num, "success": False, "latency_s": None, "error": str(e)}

    client.loop_start()

    if not connected.wait(timeout=10):
        print("  [ERROR] Initial connect timeout")
        client.loop_stop()
        try:
            client.disconnect()
        except Exception:
            pass
        return {"cycle": cycle_num, "success": False, "latency_s": None, "error": "initial_connect_timeout"}

    print(f"  Connected in {connect_ts[0] - t_start:.2f}s")
    time.sleep(1.0)

    # Force TCP RST
    t_rst = time.time()
    sock = client._sock
    if sock is None:
        client.loop_stop()
        return {"cycle": cycle_num, "success": False, "latency_s": None, "error": "sock_none"}

    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, linger_pack_rst())
        sock.close()
        print(f"  TCP RST sent at {time.strftime('%H:%M:%S')}")
    except OSError as e:
        print(f"  [WARN] RST error: {e}")
        client.loop_stop()
        return {"cycle": cycle_num, "success": False, "latency_s": None, "error": f"rst_oserror: {e}"}

    # Wait for disconnect detection
    disconnected.wait(timeout=10)

    # Manual reconnect (paho 2.x does not auto-reconnect from loop_start after external socket close)
    reconnect_ok = False
    reconnect_latency = None

    deadline = time.time() + RECONNECT_TIMEOUT_S
    while time.time() < deadline:
        try:
            client.reconnect()
            # Wait for on_connect to fire
            reconnect_wait = time.time() + 15
            while first_reconnect_ts[0] is None and time.time() < reconnect_wait:
                time.sleep(0.25)
            if first_reconnect_ts[0] is not None:
                reconnect_latency = first_reconnect_ts[0] - t_rst
                reconnect_ok = True
                print(f"  Reconnect OK — latency {reconnect_latency:.2f}s")
                break
            # on_connect didn't fire, try again
            time.sleep(1)
        except Exception as e:
            print(f"  [WARN] reconnect attempt failed: {e} — retrying in 2s")
            time.sleep(2)

    if not reconnect_ok:
        print(f"  [FAIL] Reconnect STUCK — timeout after {RECONNECT_TIMEOUT_S}s")

    client.loop_stop()
    try:
        client.disconnect()
    except Exception:
        pass
    time.sleep(0.5)

    return {
        "cycle": cycle_num,
        "success": reconnect_ok,
        "latency_s": reconnect_latency if reconnect_ok else RECONNECT_TIMEOUT_S,
        "error": None if reconnect_ok else "reconnect_timeout",
    }


def main():
    parser = argparse.ArgumentParser(description="AUT-539 TCP-RST Reconnect Test")
    parser.add_argument("--cycles", type=int, default=10)
    parser.add_argument("--keepalive", type=int, default=60)
    args = parser.parse_args()

    print(f"AUT-539 TCP-RST Test — {args.cycles} cycles, keepalive={args.keepalive}s")
    print(f"Broker: {BROKER}:{PORT}, client_id={CLIENT_ID}, paho 2.x")
    print("=" * 60)

    all_results = []
    stuck_at_cycle = None

    for i in range(1, args.cycles + 1):
        r = run_cycle(i, args.keepalive)
        all_results.append(r)
        if not r["success"] and stuck_at_cycle is None:
            stuck_at_cycle = i

    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)

    successful = [r for r in all_results if r["success"]]
    latencies = [r["latency_s"] for r in successful if r["latency_s"] is not None]

    max_lat = max(latencies) if latencies else None
    avg_lat = sum(latencies) / len(latencies) if latencies else None

    print(f"Reconnects successful : {len(successful)}/{args.cycles}")
    print(f"Reconnects failed     : {args.cycles - len(successful)}/{args.cycles}")
    if max_lat:
        print(f"Max recovery latency  : {max_lat:.2f}s")
    if avg_lat:
        print(f"Avg recovery latency  : {avg_lat:.2f}s")
    print(f"Stuck after cycle N   : {stuck_at_cycle if stuck_at_cycle else 'never'}")

    print("\nPer-cycle breakdown:")
    for r in all_results:
        status = "OK  " if r["success"] else "FAIL"
        lat = f"{r['latency_s']:.2f}s" if r["latency_s"] is not None else "N/A"
        err = f" [{r['error']}]" if r["error"] else ""
        print(f"  Cycle {r['cycle']:02d}: {status}  latency={lat}{err}")

    return 0 if len(successful) == args.cycles else 1


if __name__ == "__main__":
    sys.exit(main())
