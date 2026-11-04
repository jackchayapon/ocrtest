"""Best-effort Linux process/cgroup readings; no credentials or request content."""
from pathlib import Path


def memory_snapshot():
    result = {}
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                result["process_rss_bytes"] = int(line.split()[1]) * 1024
                break
        result["cgroup_memory_bytes"] = int(Path("/sys/fs/cgroup/memory.current").read_text())
    except (OSError, ValueError):
        pass
    return result
