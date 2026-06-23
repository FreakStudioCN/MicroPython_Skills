# Python env   : ${MICROPYTHON_VERSION_LABEL}
# -*- coding: utf-8 -*-
# @File    : timer_sched.py
# @Description : Timer-based cooperative task scheduler.
#                ISR only increments counters; main loop executes tasks.
# @License : MIT

from machine import Timer

_RUN = const(0)
_STOP = const(1)


class Scheduler:

    def __init__(self, timer_id=-1, tick_ms=100, idle_cb=None, error_cb=None):
        self._tasks = {}          # {name: {cb, interval_ms, tick_cnt, state}}
        self._tick_ms = tick_ms
        self._idle_cb = idle_cb
        self._error_cb = error_cb
        self._timer = Timer(timer_id)
        self._timer.init(period=tick_ms, callback=self._isr)

    def _isr(self, t):
        for task in self._tasks.values():
            if task['state'] == _RUN:
                task['tick_cnt'] += 1

    def add_task(self, callback, interval_ms, name=None):
        tid = name or str(id(callback))
        self._tasks[tid] = {
            'cb': callback,
            'interval_ms': interval_ms,
            'tick_cnt': 0,
            'state': _RUN,
        }
        return tid

    def remove_task(self, tid):
        self._tasks.pop(tid, None)

    def pause_task(self, tid):
        t = self._tasks.get(tid)
        if t:
            t['state'] = _STOP

    def resume_task(self, tid):
        t = self._tasks.get(tid)
        if t:
            t['state'] = _RUN
            t['tick_cnt'] = 0

    def start(self):
        while True:
            for tid, task in list(self._tasks.items()):
                if task['state'] != _RUN:
                    continue
                elapsed = task['tick_cnt'] * self._tick_ms
                if elapsed >= task['interval_ms']:
                    task['tick_cnt'] = 0
                    try:
                        task['cb']()
                    except Exception as e:
                        if self._error_cb:
                            self._error_cb(tid, e)
            if self._idle_cb:
                self._idle_cb()

    def stop(self):
        self._timer.deinit()
