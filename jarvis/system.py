"""PC state for the home HUD: processor, memory and system disk, in percent.

Read-only, standard library only (ctypes on Windows). Elsewhere only the disk is known.
"""

import ctypes
import os
import shutil
import time

_last = None  # (idle, total) from the previous call: CPU load is the change since then


def cpu_percent(sample):
    """Busy share of CPU time between two (idle, total) samples, 0-100."""
    global _last
    prev, _last = _last, sample
    if not prev or sample[1] <= prev[1]:
        return None
    return round(100 * (1 - (sample[0] - prev[0]) / (sample[1] - prev[1])))


def _windows():
    k32 = ctypes.windll.kernel32
    idle, kernel, user = (ctypes.c_ulonglong() for _ in range(3))
    k32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user))  # kernel time includes idle

    class Mem(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [(f, ctypes.c_ulonglong) for f in
                    ("total", "avail", "pagetotal", "pageavail", "virttotal", "virtavail", "extavail")]
    mem = Mem(length=ctypes.sizeof(Mem))
    k32.GlobalMemoryStatusEx(ctypes.byref(mem))
    return (idle.value, kernel.value + user.value), mem.load


def system():
    cpu = mem = None
    if os.name == "nt":
        sample, mem = _windows()
        cpu = cpu_percent(sample)
        if cpu is None:  # first call: measure over a short window
            time.sleep(0.25)
            cpu = cpu_percent(_windows()[0])
    root = os.environ.get("SystemDrive", "C:") + "\\" if os.name == "nt" else "/"
    disk = shutil.disk_usage(root)
    return {"cpu": cpu, "mem": mem, "disk": round(100 * disk.used / disk.total), "diskFreeGb": disk.free // 2**30}
