"""Maintenance task: GC check + system health monitoring.

Provides a simple tick callback for the scheduler idle slot.
Works across all three scheduler modes (Timer / asyncio / _thread).
"""

import gc


def maintenance_tick():
    """Call periodically (e.g. in scheduler idle slot or asyncio loop).

    Triggers GC when free memory drops below threshold.
    Extend with your own health checks (uptime log, error counters, etc.).
    If WDT is needed, create it in boot.py and call wdt.feed() here.
    """
    free = gc.mem_free()
    threshold = 80000

    if free < threshold:
        gc.collect()
        free_after = gc.mem_free()
        print("[maintenance] GC triggered: {} -> {} bytes free".format(
            free, free_after))
