"""Timing decorators for MicroPython tasks.

Provides:
  - timed_function: for synchronous def tick() / def loop() (Timer & Thread modes)
  - timed_coro:     for async def coro() (asyncio mode)
"""

import time


def _ticks_us():
    ticks = getattr(time, "ticks_us", None)
    if ticks is not None:
        return ticks()
    return int(time.monotonic() * 1000000)


def _ticks_diff(end, start):
    diff = getattr(time, "ticks_diff", None)
    if diff is not None:
        return diff(end, start)
    return end - start

# ── Synchronous ──────────────────────────────────────────────


def _callable_name(f):
    return getattr(f, "__name__", None) or getattr(f, "_name_", None) or "fn"


def timed_function(f):
    myname = _callable_name(f)

    def new_func(*args, **kwargs):
        t = _ticks_us()
        result = f(*args, **kwargs)
        delta = _ticks_diff(_ticks_us(), t)
        print('Function {} Time = {:6.3f}ms'.format(myname, delta / 1000))
        return result

    return new_func

# ── Asynchronous (asyncio mode) ──────────────────────────────


def timed_coro(f):
    myname = _callable_name(f)

    async def new_func(*args, **kwargs):
        t = _ticks_us()
        result = await f(*args, **kwargs)
        delta = _ticks_diff(_ticks_us(), t)
        print('Coro {} Time = {:6.3f}ms'.format(myname, delta / 1000))
        return result

    return new_func
