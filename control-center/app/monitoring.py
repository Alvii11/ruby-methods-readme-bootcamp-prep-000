"""System-level health metrics for the dashboard."""
from __future__ import annotations

import shutil
import time

import psutil

_BOOT = psutil.boot_time()


def system_metrics() -> dict:
    vm = psutil.virtual_memory()
    du = shutil.disk_usage("/")
    try:
        load1, load5, load15 = psutil.getloadavg()
    except (AttributeError, OSError):
        load1 = load5 = load15 = None
    return {
        "time": time.time(),
        "cpu_percent": psutil.cpu_percent(interval=None),
        "cpu_count": psutil.cpu_count(logical=True),
        "load": [load1, load5, load15],
        "mem_percent": vm.percent,
        "mem_used_gb": round(vm.used / 1024**3, 2),
        "mem_total_gb": round(vm.total / 1024**3, 2),
        "disk_percent": round(du.used / du.total * 100, 1),
        "disk_used_gb": round(du.used / 1024**3, 1),
        "disk_total_gb": round(du.total / 1024**3, 1),
        "uptime_hours": round((time.time() - _BOOT) / 3600, 1),
    }
