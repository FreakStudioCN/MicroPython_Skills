"""Timing decorators for MicroPython tasks.

Provides:
  - timed_function: for synchronous def tick() / def loop() (Timer & Thread modes)
  - timed_coro:     for async def coro() (asyncio mode)
"""

import time

# ── Synchronous ──────────────────────────────────────────────


def timed_function(f):
    myname = str(f).split(' ')[1]

    def new_func(*args, **kwargs):
        t = time.ticks_us()
        result = f(*args, **kwargs)
        delta = time.ticks_diff(time.ticks_us(), t)
        print('Function {} Time = {:6.3f}ms'.format(myname, delta / 1000))
        return result

    return new_func

# ── Asynchronous (asyncio mode) ──────────────────────────────


def timed_coro(f):
    myname = str(f).split(' ')[1]

    async def new_func(*args, **kwargs):
        t = time.ticks_us()
        result = await f(*args, **kwargs)
        delta = time.ticks_diff(time.ticks_us(), t)
        print('Coro {} Time = {:6.3f}ms'.format(myname, delta / 1000))
        return result

    return new_func
