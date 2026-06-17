"""
Network Helper Functions: IP validation, network scanning, discovery
"""

import asyncio
import socket
from typing import Optional


async def is_reachable(host: str, port: int, timeout: float = 5.0) -> bool:
    """
    Check if host:port is reachable.

    Args:
        host: Hostname or IP address
        port: Port number
        timeout: Timeout in seconds

    Returns:
        True if host:port is reachable, False otherwise
    """
    try:
        # Use asyncio.wait_for to add timeout
        await asyncio.wait_for(_check_connection(host, port), timeout=timeout)
        return True
    except (asyncio.TimeoutError, OSError, socket.gaierror):
        return False


async def _check_connection(host: str, port: int) -> None:
    """
    Internal helper to check connection.

    Args:
        host: Hostname or IP address
        port: Port number

    Raises:
        OSError: If connection fails

    Note:
        Uses get_running_loop() instead of deprecated get_event_loop()
        to prevent "Queue bound to different event loop" errors in Python 3.12+.
    """
    # Run socket.connect in executor to avoid blocking
    loop = asyncio.get_running_loop()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5.0)  # Socket-level timeout

    try:
        await loop.sock_connect(sock, (host, port))
    finally:
        sock.close()


async def ping(host: str, timeout: float = 5.0) -> Optional[float]:
    """
    Ping host and return latency in seconds.

    Note: This is a simple TCP connect-based ping, not ICMP.
    For ICMP ping, use system ping command or specialized library.

    Args:
        host: Hostname or IP address
        port: Port number (default: 80 for HTTP)
        timeout: Timeout in seconds

    Returns:
        Latency in seconds, or None if unreachable
    """
    import time

    start_time = time.time()
    reachable = await is_reachable(host, 80, timeout)  # Default to HTTP port

    if reachable:
        latency = time.time() - start_time
        return latency
    else:
        return None
