#!/usr/bin/env python3
"""Scotty health check — gathers system metrics, outputs JSON to stdout.

Local checks: disk usage, Docker, systemd, PostgreSQL, media mount, OpenClaw gateway.
NAS checks: Synology REST API — system info, storage/RAID/SMART, DSM updates.

Each check is isolated in try/except. One failure doesn't kill the others.
"""

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    print(json.dumps({"error": "requests not installed — run: pip install requests"}))
    sys.exit(1)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DISK_MOUNTS = {
    "root": "/",
    "fdrive": "/media/dan/fdrive",
    "edrive": "/media/dan/edrive",
}

MEDIA_MOUNT = "/mnt/media"

NAS_PASS_ENTRY = "openclaw/scotty/nas-credentials"
NAS_HOST_PASS_ENTRY = "openclaw/scotty/nas-host"
NAS_PORT = 5000
REQUEST_TIMEOUT = 10

MARCUS_TOKEN_PASS_ENTRY = "openclaw/marcus/youtube-token"

# Alert thresholds (percent)
DISK_WARN = 80
DISK_RED = 90
DISK_CRITICAL = 95


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_pass(entry):
    """Retrieve a value from the pass store."""
    try:
        result = subprocess.run(
            ["pass", "show", entry],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip()
    except Exception:
        return None


def disk_level(pct):
    """Return alert level string for a disk usage percentage."""
    if pct >= DISK_CRITICAL:
        return "critical"
    if pct >= DISK_RED:
        return "red"
    if pct >= DISK_WARN:
        return "warning"
    return "green"


# ---------------------------------------------------------------------------
# Local checks
# ---------------------------------------------------------------------------

def check_disk_usage():
    """Check disk usage for all configured mount points."""
    results = {}
    for name, path in DISK_MOUNTS.items():
        try:
            usage = shutil.disk_usage(path)
            pct = round(usage.used / usage.total * 100, 1)
            results[name] = {
                "path": path,
                "total_gb": round(usage.total / (1024 ** 3), 1),
                "used_gb": round(usage.used / (1024 ** 3), 1),
                "free_gb": round(usage.free / (1024 ** 3), 1),
                "percent_used": pct,
                "level": disk_level(pct),
            }
        except Exception as e:
            results[name] = {"path": path, "error": str(e), "level": "red"}
    return results


def check_docker():
    """Check Docker containers and disk usage."""
    result = {}

    # Running / stopped containers
    try:
        ps = subprocess.run(
            ["docker", "ps", "-a", "--format", "{{json .}}"],
            capture_output=True, text=True, timeout=15,
        )
        containers = []
        for line in ps.stdout.strip().split("\n"):
            if line.strip():
                c = json.loads(line)
                containers.append({
                    "name": c.get("Names", ""),
                    "status": c.get("Status", ""),
                    "state": c.get("State", ""),
                    "image": c.get("Image", ""),
                })
        result["containers"] = containers
    except Exception as e:
        result["containers_error"] = str(e)

    # Disk usage
    try:
        df = subprocess.run(
            ["docker", "system", "df", "--format", "{{json .}}"],
            capture_output=True, text=True, timeout=15,
        )
        disk = []
        for line in df.stdout.strip().split("\n"):
            if line.strip():
                disk.append(json.loads(line))
        result["disk_usage"] = disk
    except Exception as e:
        result["disk_usage_error"] = str(e)

    return result


def check_systemd():
    """Check for failed systemd units, filtering known-benign ones."""
    try:
        result = subprocess.run(
            ["systemctl", "list-units", "--state=failed", "--no-legend", "--plain"],
            capture_output=True, text=True, timeout=10,
        )
        lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
        failed = [l for l in lines if "casper-md5check" not in l]
        return {"failed_units": failed, "count": len(failed)}
    except Exception as e:
        return {"error": str(e)}


def check_postgres():
    """Check if PostgreSQL is accepting connections."""
    try:
        result = subprocess.run(
            ["pg_isready"],
            capture_output=True, text=True, timeout=10,
        )
        return {
            "accepting": result.returncode == 0,
            "message": result.stdout.strip(),
        }
    except Exception as e:
        return {"error": str(e)}


def check_media_mount():
    """Check if /mnt/media is mounted and has contents."""
    try:
        result = subprocess.run(
            ["mountpoint", "-q", MEDIA_MOUNT],
            capture_output=True, timeout=10,
        )
        mounted = result.returncode == 0
        contents = []
        if mounted:
            try:
                contents = os.listdir(MEDIA_MOUNT)[:10]
            except Exception:
                pass
        return {
            "path": MEDIA_MOUNT,
            "mounted": mounted,
            "sample_contents": contents,
        }
    except Exception as e:
        return {"path": MEDIA_MOUNT, "error": str(e)}


def check_openclaw_gateway():
    """Check if the OpenClaw gateway user service is running."""
    try:
        result = subprocess.run(
            ["systemctl", "--user", "is-active", "openclaw-gateway.service"],
            capture_output=True, text=True, timeout=10,
        )
        status = result.stdout.strip()
        return {"active": status == "active", "status": status}
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# NAS checks (Synology REST API)
# ---------------------------------------------------------------------------

def nas_api_call(base_url, sid, api, method, version=1, extra_params=None):
    """Make a single Synology API call and return the parsed JSON response."""
    params = {
        "api": api,
        "method": method,
        "version": version,
    }
    if sid:
        params["_sid"] = sid
    if extra_params:
        params.update(extra_params)

    resp = requests.get(
        f"{base_url}/webapi/entry.cgi",
        params=params,
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def check_nas():
    """Check Synology NAS health via REST API."""
    # Resolve host from pass
    nas_host = get_pass(NAS_HOST_PASS_ENTRY)
    if not nas_host:
        return {"error": "Could not retrieve NAS host from pass", "level": "red"}

    # Resolve credentials from pass
    creds_raw = get_pass(NAS_PASS_ENTRY)
    if not creds_raw:
        return {"error": "Could not retrieve NAS credentials from pass", "level": "red"}

    parts = creds_raw.split(":", 1)
    if len(parts) != 2:
        return {"error": "NAS credentials format error (expected user:password)", "level": "red"}

    username, password = parts
    base_url = f"http://{nas_host}:{NAS_PORT}"
    sid = None
    result = {}

    try:
        # --- Login ---
        login_resp = nas_api_call(
            base_url, None, "SYNO.API.Auth", "login", version=6,
            extra_params={
                "account": username,
                "passwd": password,
                "session": "HealthCheck",
                "format": "sid",
            },
        )
        if not login_resp.get("success"):
            error_code = login_resp.get("error", {}).get("code", "unknown")
            return {"error": f"NAS login failed (code {error_code})", "level": "red"}

        sid = login_resp["data"]["sid"]

        # --- System info ---
        try:
            sys_resp = nas_api_call(
                base_url, sid, "SYNO.Core.System", "info", version=3,
            )
            if sys_resp.get("success"):
                data = sys_resp["data"]
                temp = data.get("temperature", data.get("sys_temp", 0))
                temp_level = "green"
                if temp > 55:
                    temp_level = "red"
                elif temp > 50:
                    temp_level = "warning"
                result["system"] = {
                    "model": data.get("model", "unknown"),
                    "dsm_version": data.get("firmware_ver", "unknown"),
                    "temperature_c": temp,
                    "uptime_seconds": data.get("up_time", 0),
                    "temp_level": temp_level,
                }
        except Exception as e:
            result["system_error"] = str(e)

        # --- Storage / RAID / SMART ---
        try:
            stor_resp = nas_api_call(
                base_url, sid, "SYNO.Storage.CGI.Storage", "load_info", version=1,
            )
            if stor_resp.get("success"):
                data = stor_resp["data"]

                # Volumes
                volumes = []
                for vol in data.get("volumes", []):
                    size = vol.get("size", {})
                    total = int(size.get("total", 0))
                    used = int(size.get("used", 0))
                    pct = round(used / total * 100, 1) if total > 0 else 0
                    volumes.append({
                        "id": vol.get("id", ""),
                        "status": vol.get("status", ""),
                        "total_gb": round(total / (1024 ** 3), 1),
                        "used_gb": round(used / (1024 ** 3), 1),
                        "percent_used": pct,
                        "level": disk_level(pct),
                    })
                result["volumes"] = volumes

                # Disks / SMART
                disks = []
                for disk in data.get("disks", []):
                    smart_status = disk.get("smart_status", "unknown")
                    bad_sectors = disk.get("num_bad_sectors", 0)
                    temp = disk.get("temp", 0)
                    d_level = "green"
                    if smart_status != "normal":
                        d_level = "red"
                    elif bad_sectors > 0:
                        d_level = "warning"
                    if temp > 55:
                        d_level = "red"
                    elif temp > 50 and d_level == "green":
                        d_level = "warning"
                    disks.append({
                        "id": disk.get("id", ""),
                        "name": disk.get("name", ""),
                        "smart_status": smart_status,
                        "bad_sectors": bad_sectors,
                        "temperature_c": temp,
                        "level": d_level,
                    })
                result["disks"] = disks

                # RAID / storage pools
                raids = []
                for pool in data.get("storagePools", []):
                    raids.append({
                        "id": pool.get("id", ""),
                        "status": pool.get("status", ""),
                        "raid_type": pool.get("raidType", ""),
                    })
                result["raids"] = raids

        except Exception as e:
            result["storage_error"] = str(e)

        # --- DSM updates ---
        try:
            upd_resp = nas_api_call(
                base_url, sid, "SYNO.Core.Upgrade.Server", "check", version=1,
            )
            if upd_resp.get("success"):
                data = upd_resp["data"]
                result["update_available"] = data.get("available", False)
                if data.get("available"):
                    result["update_version"] = data.get("version", "unknown")
        except Exception as e:
            result["update_error"] = str(e)

    except requests.exceptions.ConnectionError:
        return {"error": f"NAS unreachable at {base_url}", "level": "red"}
    except requests.exceptions.Timeout:
        return {"error": f"NAS timed out at {base_url}", "level": "red"}
    except Exception as e:
        result["error"] = str(e)
        result["level"] = "red"
    finally:
        # Always logout, even on error
        if sid:
            try:
                nas_api_call(
                    base_url, sid, "SYNO.API.Auth", "logout", version=1,
                    extra_params={"session": "HealthCheck"},
                )
            except Exception:
                pass

    return result


# ---------------------------------------------------------------------------
# Agent token checks
# ---------------------------------------------------------------------------

def check_marcus_youtube_token():
    """Validate Marcus's YouTube OAuth refresh token via a token refresh request.

    Uses raw HTTP — no Google client libraries required.
    """
    token_json_str = get_pass(MARCUS_TOKEN_PASS_ENTRY)
    if not token_json_str:
        return {"valid": False, "error": "Could not retrieve token from pass", "level": "red"}

    try:
        token_data = json.loads(token_json_str)
    except json.JSONDecodeError as e:
        return {"valid": False, "error": f"Token JSON parse error: {e}", "level": "red"}

    refresh_token = token_data.get("refresh_token")
    client_id = token_data.get("client_id")
    client_secret = token_data.get("client_secret")
    token_uri = token_data.get("token_uri", "https://oauth2.googleapis.com/token")

    if not all([refresh_token, client_id, client_secret]):
        return {"valid": False, "error": "Token missing required fields", "level": "red"}

    try:
        resp = requests.post(token_uri, data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        }, timeout=REQUEST_TIMEOUT)

        if resp.status_code == 200:
            return {"valid": True, "level": "green"}

        error_body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        error_desc = error_body.get("error_description", error_body.get("error", f"HTTP {resp.status_code}"))
        return {"valid": False, "error": error_desc, "level": "red"}

    except requests.exceptions.Timeout:
        return {"valid": False, "error": "Google token endpoint timed out", "level": "warning"}
    except requests.exceptions.ConnectionError:
        return {"valid": False, "error": "Could not reach Google token endpoint", "level": "warning"}
    except Exception as e:
        return {"valid": False, "error": str(e), "level": "red"}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hostname": os.uname().nodename,
    }

    # Local checks
    report["disks"] = check_disk_usage()
    report["docker"] = check_docker()
    report["systemd"] = check_systemd()
    report["postgres"] = check_postgres()
    report["media_mount"] = check_media_mount()
    report["openclaw_gateway"] = check_openclaw_gateway()

    # NAS checks (isolated — NAS failure doesn't affect local results)
    report["nas"] = check_nas()

    # Agent token checks
    report["marcus_youtube_token"] = check_marcus_youtube_token()

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
