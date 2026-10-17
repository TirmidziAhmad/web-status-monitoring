"""Health checker module for HTTP/HTTPS endpoints and TCP ports."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
import logging
import socket
import time
from urllib.parse import urlparse

import httpx

logger = logging.getLogger("cpanel_monitor.checker")


@dataclass
class CheckResult:
    target: str
    is_up: bool
    status_code: int | None
    latency_ms: float
    error_message: str | None
    checked_at: datetime

    @property
    def status_summary(self) -> str:
        if self.is_up:
            code_str = f"HTTP {self.status_code}" if self.status_code else "TCP OK"
            return f"UP ({code_str}, {self.latency_ms:.0f}ms)"
        if self.status_code and self.status_code >= 500:
            return f"DOWN (HTTP {self.status_code} - {self.error_message})"
        return f"DOWN ({self.error_message or 'Unreachable'})"


async def check_tcp_port(host: str, port: int, timeout: float = 5.0) -> tuple[bool, float, str | None]:
    """Check connectivity to a TCP host and port."""
    start_time = time.perf_counter()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout,
        )
        latency_ms = (time.perf_counter() - start_time) * 1000
        writer.close()
        await writer.wait_closed()
        return True, latency_ms, None
    except asyncio.TimeoutError:
        return False, (timeout * 1000), "Connection timed out"
    except (ConnectionRefusedError, socket.gaierror, OSError) as e:
        latency_ms = (time.perf_counter() - start_time) * 1000
        return False, latency_ms, str(e)


async def check_http_target(
    url: str,
    timeout: float = 10.0,
    verify_ssl: bool = False,
) -> CheckResult:
    """Check HTTP/HTTPS target availability and response status.
    
    verify_ssl is set to False by default to prevent self-signed/cPanel internal SSL
    from falsely reporting the server as down.
    """
    start_time = time.perf_counter()
    now = datetime.now()

    # User-agent mimics a health monitor
    headers = {
        "User-Agent": "cPanel-Health-Monitor/1.0 (+https://telegram.org)",
        "Accept": "*/*",
    }

    try:
        async with httpx.AsyncClient(
            verify=verify_ssl,
            timeout=httpx.Timeout(timeout, connect=timeout),
            follow_redirects=True,
        ) as client:
            response = await client.get(url, headers=headers)
            latency_ms = (time.perf_counter() - start_time) * 1000

            # 2xx and 3xx are clearly UP
            # 4xx (like 401 Unauthorized for cPanel login or basic auth) means server is UP and responding
            # 5xx (500, 502, 503, 504) means server/application error -> DOWN
            if response.status_code < 500:
                return CheckResult(
                    target=url,
                    is_up=True,
                    status_code=response.status_code,
                    latency_ms=latency_ms,
                    error_message=None,
                    checked_at=now,
                )
            else:
                return CheckResult(
                    target=url,
                    is_up=False,
                    status_code=response.status_code,
                    latency_ms=latency_ms,
                    error_message=f"Server Error {response.status_code} ({response.reason_phrase})",
                    checked_at=now,
                )

    except httpx.TimeoutException:
        latency_ms = (time.perf_counter() - start_time) * 1000
        return CheckResult(
            target=url,
            is_up=False,
            status_code=None,
            latency_ms=latency_ms,
            error_message="Request Timeout (Server tidak merespons)",
            checked_at=now,
        )

    except httpx.ConnectError as e:
        latency_ms = (time.perf_counter() - start_time) * 1000
        err_str = str(e) or "Connection refused / Host unreachable"
        return CheckResult(
            target=url,
            is_up=False,
            status_code=None,
            latency_ms=latency_ms,
            error_message=f"Koneksi Gagal ({err_str})",
            checked_at=now,
        )

    except httpx.RequestError as e:
        latency_ms = (time.perf_counter() - start_time) * 1000
        return CheckResult(
            target=url,
            is_up=False,
            status_code=None,
            latency_ms=latency_ms,
            error_message=f"Jaringan Error ({e.__class__.__name__})",
            checked_at=now,
        )

    except Exception as e:
        latency_ms = (time.perf_counter() - start_time) * 1000
        logger.exception("Unexpected error while checking %s: %s", url, e)
        return CheckResult(
            target=url,
            is_up=False,
            status_code=None,
            latency_ms=latency_ms,
            error_message=f"Error ({str(e)})",
            checked_at=now,
        )


async def check_target(url: str, timeout: float = 10.0) -> CheckResult:
    """Smart target dispatcher: checks TCP or HTTP based on URL scheme."""
    parsed = urlparse(url)
    if parsed.scheme == "tcp":
        host = parsed.hostname or ""
        port = parsed.port or 80
        is_up, latency_ms, err = await check_tcp_port(host, port, timeout=timeout)
        return CheckResult(
            target=url,
            is_up=is_up,
            status_code=None,
            latency_ms=latency_ms,
            error_message=err,
            checked_at=datetime.now(),
        )

    return await check_http_target(url, timeout=timeout)


async def check_all_targets(targets: list[str], timeout: float = 10.0) -> list[CheckResult]:
    """Check multiple targets concurrently."""
    tasks = [check_target(target, timeout=timeout) for target in targets]
    return await asyncio.gather(*tasks)
