"""Rotating log module (MicroPython + CPython dual-platform).

File naming: {log_dir}/{prefix}_0.log, {prefix}_1.log, ...
Rotation: switches to next file when exceeding lines_per_file (cyclic).
"""

import os

try:
    from time import ticks_ms  # noqa: F401 — MicroPython canary import
    _IS_MICROPYTHON = True
except ImportError:
    _IS_MICROPYTHON = False


def _get_mtime(path):
    try:
        if _IS_MICROPYTHON:
            return os.stat(path)[8]
        else:
            return int(os.stat(path).st_mtime)
    except OSError:
        return 0


def _mkdir(path):
    if _IS_MICROPYTHON:
        try:
            os.mkdir(path)
        except OSError:
            pass
    else:
        os.makedirs(path, exist_ok=True)


class _RotatingFile:

    def __init__(self, log_dir, max_files, lines_per_file, prefix):
        self._log_dir = log_dir
        self._max_files = max_files
        self._lines_per_file = lines_per_file
        self._prefix = prefix
        self._index = 0
        self._line_count = 0
        self._file = None
        self._init()

    def _init(self):
        _mkdir(self._log_dir)
        latest_mtime = 0
        latest_index = 0
        for i in range(self._max_files):
            mtime = _get_mtime(self._get_path(i))
            if mtime > latest_mtime:
                latest_mtime = mtime
                latest_index = i
        self._index = latest_index
        try:
            with open(self._get_path(self._index), "r") as f:
                self._line_count = sum(1 for _ in f)
        except OSError:
            self._line_count = 0

    def _get_path(self, index):
        return "{}/{}_{}{}".format(self._log_dir, self._prefix, index, ".log")

    def write(self, line):
        if self._line_count >= self._lines_per_file:
            if self._file:
                self._file.close()
                self._file = None
            self._index = (self._index + 1) % self._max_files
            self._line_count = 0
            self._file = open(self._get_path(self._index), "w")

        if self._file is None:
            self._file = open(self._get_path(self._index), "a")

        try:
            self._file.write(line + "\n")
            self._file.flush()
            self._line_count += 1
        except Exception:
            pass

    def close(self):
        if self._file:
            self._file.close()
            self._file = None


if _IS_MICROPYTHON:
    def install(log_dir, max_files=4, lines_per_file=150, prefix="run",
                fmt="%(levelname)s:%(name)s:%(message)s"):
        """MicroPython: monkey-patch Logger.log to redirect to rotating files.

        WARNING: After install, ALL logger output (debug/info/warning/error)
        goes ONLY to /log/run_*.log files.  The original stderr channel is
        cut off — nothing from the logger will appear on the REPL.  Use
        print() for REPL-visible output alongside logger calls.
        """
        from . import logging as _logging

        _rot = _RotatingFile(log_dir, max_files, lines_per_file, prefix)

        def _patched_log(self, level, message, *args):
            if level < self.level:
                return
            try:
                if args:
                    message = message % args
                record = {
                    "levelname": _logging._level_str.get(level, str(level)),
                    "level": level,
                    "message": message,
                    "name": self.name,
                }
                _rot.write(fmt % record)
            except Exception:
                pass

        _logging.Logger.log = _patched_log

else:
    import logging

    class RotatingFileHandler(logging.Handler):

        def __init__(self, log_dir, max_files=4, lines_per_file=150, prefix="run"):
            super().__init__()
            self._rot = _RotatingFile(log_dir, max_files, lines_per_file, prefix)

        def emit(self, record):
            try:
                self._rot.write(self.format(record))
            except Exception:
                pass

        def close(self):
            self._rot.close()
            super().close()
