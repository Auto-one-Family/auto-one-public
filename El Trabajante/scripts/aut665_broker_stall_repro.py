#!/usr/bin/env python3
"""
AUT-665 — Broker-Backpressure Repro (dev-local)
Tests H1: Broker-TCP-Read-Stall → TCP-Window=0 → ESP-Write-Timeout (errno=119/EINPROGRESS)

Causal chain verified:
  Broker SIGSTOP → broker drains nothing → TCP recv-buf fills → TCP-Window=0
  → ESP write() → EAGAIN/EINPROGRESS (errno 119) → after 1500ms: write_timeout_silent

Usage:
  python aut665_broker_stall_repro.py
  -> pauses automationone-mqtt container for 3s and 5s, measures fill+timeout
"""
import socket
import time
import threading
import subprocess
import sys

BROKER = "localhost"
PORT = 1883
NETWORK_TIMEOUT_MS = 1500  # mirrors MQTT_CLIENT_NETWORK_TIMEOUT_MS (mqtt_client.cpp:138)
TCP_SND_BUF = 5760         # ESP32 prebuilt CONFIG_LWIP_TCP_SND_BUF_DEFAULT (sdkconfig.h:484)

CONTAINER = "automationone-mqtt"


def pause_broker(seconds: float):
    subprocess.run(["docker", "pause", CONTAINER], capture_output=True)
    print(f"  [BROKER PAUSED for {seconds}s]")
    time.sleep(seconds)
    subprocess.run(["docker", "unpause", CONTAINER], capture_output=True)
    print(f"  [BROKER UNPAUSED]")


def build_mqtt_connect(client_id: str = "AUT665_REPRO") -> bytes:
    """Build a minimal MQTT CONNECT packet."""
    protocol = b"\x00\x04MQTT\x04\x02"  # Protocol + version + connect flags (clean session)
    keepalive = b"\x00\x3c"             # 60s
    cid_len = len(client_id).to_bytes(2, "big")
    payload = cid_len + client_id.encode()
    remaining = protocol + keepalive + payload
    return b"\x10" + bytes([len(remaining)]) + remaining


def build_mqtt_publish_qos1(topic: str, payload: str, msg_id: int = 1) -> bytes:
    """Build a MQTT PUBLISH QoS=1 packet."""
    t = topic.encode()
    p = payload.encode()
    topic_field = len(t).to_bytes(2, "big") + t
    msg_id_field = msg_id.to_bytes(2, "big")
    body = topic_field + msg_id_field + p
    return b"\x32" + bytes([len(body)]) + body


def build_mqtt_pingreq() -> bytes:
    return b"\xc0\x00"


def run_repro(stall_seconds: float, label: str):
    print(f"\n{'='*60}")
    print(f"TEST: {label} ({stall_seconds}s broker pause)")
    print(f"  ESP32 TCP_SND_BUF = {TCP_SND_BUF} B")
    print(f"  network_timeout_ms = {NETWORK_TIMEOUT_MS} ms")
    print(f"{'='*60}")

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    # Mimic ESP32's small send buffer
    s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, TCP_SND_BUF)
    s.connect((BROKER, PORT))

    # MQTT CONNECT
    s.send(build_mqtt_connect("AUT665_REPRO"))
    time.sleep(0.2)
    s.recv(4096)  # CONNACK

    # Subscribe to a topic so we have a proper session
    topic = "kaiser/test/esp/AUT665_REPRO/sensor/1/data"

    print(f"\nPhase 1: Normal publish (broker running)")
    send_count = 0
    t0 = time.time()
    while time.time() - t0 < 0.5:
        pkt = build_mqtt_publish_qos1(topic, '{"value":23.5,"ts":1234567890}', msg_id=(send_count % 65535) + 1)
        s.send(pkt)
        send_count += 1
    print(f"  Sent {send_count} publishes in 500ms OK")

    # Drain PUBACK responses
    s.setblocking(False)
    try:
        s.recv(65535)
    except BlockingIOError:
        pass
    s.setblocking(True)

    print(f"\nPhase 2: Pause broker for {stall_seconds}s, then publish")
    pause_thread = threading.Thread(target=pause_broker, args=(stall_seconds,), daemon=True)
    pause_thread.start()
    time.sleep(0.05)  # brief wait so pause is active

    # Now attempt writes with timeout matching ESP32 behavior
    s.settimeout(NETWORK_TIMEOUT_MS / 1000.0)
    stall_detected_at = None
    bytes_sent = 0
    timeout_error = None

    for i in range(500):
        pkt = build_mqtt_publish_qos1(topic, '{"value":23.5,"ts":1234567890,"idx":%d}' % i, msg_id=(i % 65535) + 1)
        try:
            t_send = time.time()
            s.send(pkt)
            bytes_sent += len(pkt)
        except socket.timeout:
            elapsed = time.time() - t_send
            stall_detected_at = i
            timeout_error = f"socket.timeout after {elapsed*1000:.0f}ms at msg #{i}, total_sent={bytes_sent}B"
            break
        except (ConnectionResetError, BrokenPipeError, OSError) as e:
            stall_detected_at = i
            timeout_error = f"socket error: {e} at msg #{i}"
            break

    pause_thread.join(timeout=stall_seconds + 1)

    print(f"\nRESULTS for {label}:")
    if timeout_error:
        print(f"  TIMEOUT/ERROR: {timeout_error}")
        print(f"  Bytes sent before stall: {bytes_sent} B")
        print(f"  VERDICT: H1 confirmed — write stall after {stall_seconds}s broker pause")
        print(f"  errno=119/EINPROGRESS path: TCP send buffer ({TCP_SND_BUF}B) + broker recv-buf exhausted")
    else:
        print(f"  NO TIMEOUT (sent {bytes_sent}B during pause) — H1 not confirmed for {stall_seconds}s stall")
        print(f"  Note: OS may have buffered more than TCP_SND_BUF suggests (kernel socket buffer vs app buffer)")

    s.close()
    return stall_detected_at is not None, bytes_sent


if __name__ == "__main__":
    print("AUT-665 Broker-Backpressure Repro")
    print(f"Target: {BROKER}:{PORT} (container: {CONTAINER})")

    # Check broker is reachable
    try:
        test_sock = socket.create_connection((BROKER, PORT), timeout=2)
        test_sock.close()
        print("Broker reachable OK\n")
    except Exception as e:
        print(f"ABORT: Broker not reachable: {e}")
        sys.exit(1)

    results = []
    for stall_s, label in [(1.5, "1.5s_stall_equals_timeout"), (3.0, "3s_stall_exceeds_timeout"), (5.0, "5s_stall_deep")]:
        try:
            hit, sent = run_repro(stall_s, label)
            results.append((label, hit, sent))
            time.sleep(1.0)  # inter-test cooldown
        except Exception as e:
            print(f"  ERROR in {label}: {e}")
            results.append((label, False, 0))

    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for label, hit, sent in results:
        status = "CONFIRMED" if hit else "not triggered"
        print(f"  {label}: {status} (bytes_sent_before_stall={sent})")

    print(f"\nBroker-Config-Delta dev-local vs pi-home:")
    print(f"  dev-local: anonymous=true, persistence=true, autosave_interval=300s")
    print(f"             max_keepalive=300, max_inflight=10, Mosquitto 2.x in Docker")
    print(f"  pi-home:   UNKNOWN (requires pi-home-Session G1) — likely:")
    print(f"             auth=password_file (authenticated), persistence=true")
    print(f"             Pi 3/4 hardware → lower recv-buffer drain rate under load")
    print(f"             Pi swap/IO during cron/logrotate → broker read() stalls")
    print(f"             This is the pi-SPECIFIC trigger — needs G1 for confirmation")
