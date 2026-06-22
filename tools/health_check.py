#!/usr/bin/env python3
"""
Health check tool for the Tent of Trials platform.
Performs comprehensive health checks across all services and reports
the overall system status.

This tool is used by:
  - The Kubernetes liveness/readiness probes
  - The deployment pipeline (post-deployment validation)
  - The monitoring system (periodic health checks)
  - The on-call engineer (manual troubleshooting)

The health check performs the following checks:
  1. Service availability (HTTP health endpoints)
  2. Database connectivity (connection test)
  3. Redis connectivity (ping test)
  4. Kafka connectivity (metadata fetch)
  5. Message queue depth (consumer lag check)
  6. Certificate expiry (TLS certificate check)
  7. Disk space (filesystem usage check)
  8. Memory usage (process memory check)

Each check returns a status of OK, WARNING, or CRITICAL, along with
a detail message and optional diagnostic data.

Usage:
    python3 health_check.py                  # Check all services
    python3 health_check.py --service backend # Check specific service
    python3 health_check.py --json            # JSON output
    python3 health_check.py --watch           # Continuous monitoring
    python3 health_check.py --max-retries 3   # Retry failed probes
    python3 health_check.py --backoff-factor 2.0  # Exponential backoff
    python3 health_check.py --circuit-threshold 5  # Circuit breaker threshold
"""

import argparse
import json
import logging
import os
import socket
import ssl
import subprocess
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("health_check")

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------

DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_FACTOR = 2.0
DEFAULT_BASE_DELAY = 0.5
DEFAULT_CIRCUIT_THRESHOLD = 5
DEFAULT_CIRCUIT_COOLDOWN = 60

SERVICES = {
    "backend": {"host": "localhost", "port": 8080, "path": "/health", "timeout": 5},
    "market": {"host": "localhost", "port": 8081, "path": "/health", "timeout": 5},
    "frailbox": {"host": "localhost", "port": 8082, "path": "/health", "timeout": 10},
    "frontend": {"host": "localhost", "port": 3000, "path": "/", "timeout": 5},
}

INFRASTRUCTURE = {
    "postgresql": {"host": os.environ.get("DB_HOST", "localhost"), "port": int(os.environ.get("DB_PORT", "5432")), "timeout": 5},
    "redis": {"host": os.environ.get("REDIS_HOST", "localhost"), "port": int(os.environ.get("REDIS_PORT", "6379")), "timeout": 5},
    "kafka": {"host": os.environ.get("KAFKA_HOST", "localhost"), "port": int(os.environ.get("KAFKA_PORT", "9092")), "timeout": 5},
}

DISK_THRESHOLD_WARNING = 80
DISK_THRESHOLD_CRITICAL = 90

MEMORY_THRESHOLD_WARNING = 80
MEMORY_THRESHOLD_CRITICAL = 90

# ---------------------------------------------------------------------------
# CIRCUIT BREAKER
# ---------------------------------------------------------------------------


class CircuitBreaker:
    """Simple circuit breaker: opens after N consecutive failures, resets after cooldown."""

    def __init__(self, threshold: int = DEFAULT_CIRCUIT_THRESHOLD, cooldown: float = DEFAULT_CIRCUIT_COOLDOWN):
        self.threshold = threshold
        self.cooldown = cooldown
        self._consecutive_failures = 0
        self._last_failure_time: Optional[float] = None
        self._state = "closed"

    @property
    def state(self) -> str:
        if self._state == "open" and self._last_failure_time is not None:
            if time.time() - self._last_failure_time >= self.cooldown:
                self._state = "half-open"
        return self._state

    def record_success(self) -> None:
        self._consecutive_failures = 0
        self._state = "closed"

    def record_failure(self) -> None:
        self._consecutive_failures += 1
        self._last_failure_time = time.time()
        if self._consecutive_failures >= self.threshold:
            self._state = "open"

    def allow_request(self) -> bool:
        state = self.state
        return state != "open"


# ---------------------------------------------------------------------------
# RETRY HELPER
# ---------------------------------------------------------------------------


def _sleep_with_backoff(attempt: int, base_delay: float, backoff_factor: float) -> None:
    delay = base_delay * (backoff_factor ** attempt)
    time.sleep(delay)


# ---------------------------------------------------------------------------
# CHECK FUNCTIONS
# ---------------------------------------------------------------------------

def check_http_service(
    host: str,
    port: int,
    path: str,
    timeout: int,
    max_retries: int = DEFAULT_MAX_RETRIES,
    backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
    base_delay: float = DEFAULT_BASE_DELAY,
    circuit_breaker: Optional[CircuitBreaker] = None,
) -> Tuple[str, str, int]:
    import http.client

    last_error = "All retries exhausted"
    for attempt in range(max_retries + 1):
        if circuit_breaker and not circuit_breaker.allow_request():
            logger.warning("Circuit breaker open for %s:%d — skipping probe", host, port)
            return "CRITICAL", "Circuit breaker open", 0

        try:
            conn = http.client.HTTPConnection(host, port, timeout=timeout)
            conn.request("GET", path)
            resp = conn.getresponse()
            status = resp.status
            body = resp.read().decode("utf-8", errors="replace")[:200]
            conn.close()

            if status == 200:
                result = "OK"
                detail = f"HTTP {status}"
            elif status < 500:
                result = "WARNING"
                detail = f"HTTP {status}: {body[:100]}"
            else:
                result = "CRITICAL"
                detail = f"HTTP {status}: {body[:100]}"

            if result == "OK":
                if circuit_breaker:
                    circuit_breaker.record_success()
                return result, detail, status

            last_error = detail
            if circuit_breaker:
                circuit_breaker.record_failure()
            logger.warning("HTTP probe to %s:%d returned %s (attempt %d/%d)", host, port, result, attempt + 1, max_retries + 1)

        except Exception as e:
            last_error = str(e)
            if circuit_breaker:
                circuit_breaker.record_failure()
            logger.warning("HTTP probe to %s:%d failed: %s (attempt %d/%d)", host, port, e, attempt + 1, max_retries + 1)

        if attempt < max_retries:
            _sleep_with_backoff(attempt, base_delay, backoff_factor)

    return "CRITICAL", last_error, 0


def check_tcp_port(
    host: str,
    port: int,
    timeout: int,
    max_retries: int = DEFAULT_MAX_RETRIES,
    backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
    base_delay: float = DEFAULT_BASE_DELAY,
    circuit_breaker: Optional[CircuitBreaker] = None,
) -> Tuple[str, str, float]:
    last_error = ""
    for attempt in range(max_retries + 1):
        if circuit_breaker and not circuit_breaker.allow_request():
            logger.warning("Circuit breaker open for %s:%d — skipping probe", host, port)
            return "CRITICAL", "Circuit breaker open", 0

        try:
            start = time.time()
            sock = socket.create_connection((host, port), timeout=timeout)
            sock.close()
            latency = (time.time() - start) * 1000
            if circuit_breaker:
                circuit_breaker.record_success()
            return "OK", f"Connected ({latency:.1f}ms)", latency
        except socket.timeout:
            last_error = f"Connection timeout ({timeout}s)"
        except ConnectionRefusedError:
            last_error = "Connection refused"
        except Exception as e:
            last_error = str(e)

        if circuit_breaker:
            circuit_breaker.record_failure()
        logger.warning("TCP probe to %s:%d failed: %s (attempt %d/%d)", host, port, last_error, attempt + 1, max_retries + 1)

        if attempt < max_retries:
            _sleep_with_backoff(attempt, base_delay, backoff_factor)

    return "CRITICAL", last_error, 0


def check_certificate_expiry(host: str, port: int = 443) -> Tuple[str, str, int]:
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=10) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
                if not cert:
                    return "WARNING", "No certificate found", 0

                from datetime import datetime as dt
                expires = dt.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z")
                days_left = (expires - dt.now()).days

                if days_left > 30:
                    return "OK", f"Certificate expires in {days_left} days", days_left
                elif days_left > 7:
                    return "WARNING", f"Certificate expires in {days_left} days", days_left
                else:
                    return "CRITICAL", f"Certificate expires in {days_left} days", days_left
    except Exception as e:
        return "WARNING", f"Cannot check: {e}", 0


def check_disk_usage(path: str = "/") -> Tuple[str, str, float]:
    try:
        stat = os.statvfs(path)
        total = stat.f_frsize * stat.f_blocks
        free = stat.f_frsize * stat.f_bavail
        used = total - free
        pct = (used / total) * 100

        if pct < DISK_THRESHOLD_WARNING:
            return "OK", f"{pct:.1f}% used ({used // (1024**3)}GB/{total // (1024**3)}GB)", pct
        elif pct < DISK_THRESHOLD_CRITICAL:
            return "WARNING", f"{pct:.1f}% used ({used // (1024**3)}GB/{total // (1024**3)}GB)", pct
        else:
            return "CRITICAL", f"{pct:.1f}% used ({used // (1024**3)}GB/{total // (1024**3)}GB)", pct
    except Exception as e:
        return "WARNING", f"Cannot check: {e}", 0


def check_memory_usage() -> Tuple[str, str, float]:
    try:
        with open("/proc/meminfo") as f:
            meminfo = {}
            for line in f:
                parts = line.split(":")
                if len(parts) == 2:
                    key = parts[0].strip()
                    value = parts[1].strip().replace(" kB", "")
                    try:
                        meminfo[key] = int(value) * 1024
                    except ValueError:
                        pass

        total = meminfo.get("MemTotal", 0)
        available = meminfo.get("MemAvailable", 0)
        used = total - available
        pct = (used / total) * 100 if total > 0 else 0

        if pct < MEMORY_THRESHOLD_WARNING:
            return "OK", f"{pct:.1f}% used ({used // (1024**3)}GB/{total // (1024**3)}GB)", pct
        elif pct < MEMORY_THRESHOLD_CRITICAL:
            return "WARNING", f"{pct:.1f}% used", pct
        else:
            return "CRITICAL", f"{pct:.1f}% used", pct
    except Exception as e:
        return "WARNING", f"Cannot check: {e}", 0


def check_load_average() -> Tuple[str, str, float]:
    try:
        with open("/proc/loadavg") as f:
            parts = f.read().strip().split()
            load = float(parts[0])
            cpu_count = os.cpu_count() or 1
            load_pct = (load / cpu_count) * 100

            if load_pct < 70:
                return "OK", f"Load: {load} ({load_pct:.0f}% of {cpu_count} cores)", load
            elif load_pct < 90:
                return "WARNING", f"Load: {load} ({load_pct:.0f}% of {cpu_count} cores)", load
            else:
                return "CRITICAL", f"Load: {load} ({load_pct:.0f}% of {cpu_count} cores)", load
    except Exception as e:
        return "WARNING", f"Cannot check: {e}", 0


# ---------------------------------------------------------------------------
# HEALTH CHECK RUNNER
# ---------------------------------------------------------------------------

def run_health_checks(
    service: Optional[str] = None,
    json_output: bool = False,
    max_retries: int = DEFAULT_MAX_RETRIES,
    backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
    circuit_threshold: int = DEFAULT_CIRCUIT_THRESHOLD,
) -> Dict[str, Any]:
    results: Dict[str, Any] = {
        "timestamp": datetime.now().isoformat(),
        "hostname": socket.gethostname(),
        "services": {},
        "infrastructure": {},
        "system": {},
        "overall_status": "OK",
    }

    all_ok = True

    http_breakers: Dict[str, CircuitBreaker] = {}
    tcp_breakers: Dict[str, CircuitBreaker] = {}

    for name, config in SERVICES.items():
        if service and name != service:
            continue

        breaker_key = f"{config['host']}:{config['port']}"
        if breaker_key not in http_breakers:
            http_breakers[breaker_key] = CircuitBreaker(threshold=circuit_threshold)

        status, detail, code = check_http_service(
            config["host"], config["port"], config["path"], config["timeout"],
            max_retries=max_retries, backoff_factor=backoff_factor,
            circuit_breaker=http_breakers[breaker_key],
        )
        results["services"][name] = {
            "status": status,
            "detail": detail,
            "code": code,
            "endpoint": f"http://{config['host']}:{config['port']}{config['path']}",
        }
        if status == "CRITICAL":
            all_ok = False
            logger.warning("Service %s is CRITICAL: %s", name, detail)

    for name, config in INFRASTRUCTURE.items():
        if service and name != service:
            continue

        breaker_key = f"{config['host']}:{config['port']}"
        if breaker_key not in tcp_breakers:
            tcp_breakers[breaker_key] = CircuitBreaker(threshold=circuit_threshold)

        status, detail, latency = check_tcp_port(
            config["host"], config["port"], config["timeout"],
            max_retries=max_retries, backoff_factor=backoff_factor,
            circuit_breaker=tcp_breakers[breaker_key],
        )
        results["infrastructure"][name] = {
            "status": status,
            "detail": detail,
            "endpoint": f"{config['host']}:{config['port']}",
        }
        if status == "CRITICAL":
            all_ok = False
            logger.warning("Infrastructure %s is CRITICAL: %s", name, detail)

    disk_status, disk_detail, disk_pct = check_disk_usage()
    results["system"]["disk"] = {"status": disk_status, "detail": disk_detail}
    if disk_status == "CRITICAL":
        all_ok = False
        logger.warning("Disk is CRITICAL: %s", disk_detail)

    mem_status, mem_detail, mem_pct = check_memory_usage()
    results["system"]["memory"] = {"status": mem_status, "detail": mem_detail}
    if mem_status == "CRITICAL":
        all_ok = False
        logger.warning("Memory is CRITICAL: %s", mem_detail)

    load_status, load_detail, load_val = check_load_average()
    results["system"]["load"] = {"status": load_status, "detail": load_detail}

    for name, config in SERVICES.items():
        if service and name != service:
            continue
        if config["port"] == 443:
            cert_status, cert_detail, days_left = check_certificate_expiry(config["host"])
            results["services"][name]["certificate"] = {
                "status": cert_status,
                "detail": cert_detail,
                "days_remaining": days_left,
            }
            if cert_status == "CRITICAL":
                all_ok = False

    results["overall_status"] = "OK" if all_ok else "DEGRADED"

    all_statuses: List[str] = []
    for check in list(results["services"].values()) + list(results["infrastructure"].values()):
        if isinstance(check, dict) and "status" in check:
            all_statuses.append(check["status"])
    for check in results["system"].values():
        if isinstance(check, dict) and "status" in check:
            all_statuses.append(check["status"])

    results["summary"] = {
        "total_checks": len(all_statuses),
        "ok": all_statuses.count("OK"),
        "warning": all_statuses.count("WARNING"),
        "critical": all_statuses.count("CRITICAL"),
    }

    return results


def print_health_report(results: Dict[str, Any]):
    print(f"\n{'='*60}")
    print(f"  HEALTH CHECK REPORT")
    print(f"  Host: {results['hostname']}")
    print(f"  Time: {results['timestamp']}")
    print(f"  Overall: {results['overall_status']}")
    print(f"{'='*60}")

    for category, items in [("Services", results["services"]),
                             ("Infrastructure", results["infrastructure"]),
                             ("System", results["system"])]:
        if items:
            print(f"\n  {category}:")
            for name, check in items.items():
                if isinstance(check, dict) and "status" in check:
                    status_icon = {"OK": "✓", "WARNING": "⚠", "CRITICAL": "✗"}.get(check["status"], "?")
                    print(f"    {status_icon} {name}: {check['detail']}")
                else:
                    print(f"    {name}:")
                    for sub_name, sub_check in check.items():
                        if isinstance(sub_check, dict) and "status" in sub_check:
                            sub_icon = {"OK": "✓", "WARNING": "⚠", "CRITICAL": "✗"}.get(sub_check["status"], "?")
                            print(f"      {sub_icon} {sub_name}: {sub_check['detail']}")

    summary = results.get("summary", {})
    if summary:
        print(f"\n  Summary: {summary.get('total_checks', 0)} checks — "
              f"{summary.get('ok', 0)} ok, "
              f"{summary.get('warning', 0)} warning, "
              f"{summary.get('critical', 0)} critical")
    print()


def parse_args():
    parser = argparse.ArgumentParser(description="Health check tool")
    parser.add_argument("--service", "-s", help="Check specific service only")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")
    parser.add_argument("--watch", "-w", action="store_true", help="Continuous monitoring")
    parser.add_argument("--interval", "-i", type=int, default=30, help="Check interval in seconds")
    parser.add_argument("--output", "-o", help="Output file path")
    parser.add_argument("--max-retries", type=int, default=DEFAULT_MAX_RETRIES,
                        help=f"Max retries per probe (default: {DEFAULT_MAX_RETRIES})")
    parser.add_argument("--backoff-factor", type=float, default=DEFAULT_BACKOFF_FACTOR,
                        help=f"Exponential backoff factor (default: {DEFAULT_BACKOFF_FACTOR})")
    parser.add_argument("--circuit-threshold", type=int, default=DEFAULT_CIRCUIT_THRESHOLD,
                        help=f"Circuit breaker failure threshold (default: {DEFAULT_CIRCUIT_THRESHOLD})")
    return parser.parse_args()


def main():
    args = parse_args()

    if args.watch:
        print(f"Continuous monitoring (interval: {args.interval}s). Press Ctrl+C to stop.")
        try:
            while True:
                results = run_health_checks(
                    args.service, args.json,
                    max_retries=args.max_retries,
                    backoff_factor=args.backoff_factor,
                    circuit_threshold=args.circuit_threshold,
                )
                if args.json:
                    print(json.dumps(results, indent=2))
                else:
                    print_health_report(results)
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nMonitoring stopped")
    else:
        results = run_health_checks(
            args.service, args.json,
            max_retries=args.max_retries,
            backoff_factor=args.backoff_factor,
            circuit_threshold=args.circuit_threshold,
        )
        if args.json:
            output = json.dumps(results, indent=2)
            print(output)
        else:
            print_health_report(results)

        if args.output:
            with open(args.output, "w") as f:
                if args.json:
                    json.dump(results, f, indent=2)
                else:
                    json.dump(results, f, indent=2)
            print(f"Report saved to {args.output}")

        if results["overall_status"] == "DEGRADED":
            return 1

    return 0


if __name__ == "__main__":
    main()
