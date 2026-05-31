# libs/logger/__init__.py
# Re-export logging and rotating_logger for convenient import.
from .logging import (
    CRITICAL, ERROR, WARNING, INFO, DEBUG, NOTSET,
    basicConfig, getLogger, setLevel,
    debug, info, warning, error, critical, exception,
)
from .rotating_logger import install as install_rotating
