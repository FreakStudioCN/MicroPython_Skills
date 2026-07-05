# Production Driver P0 Normalization

Use this checklist after hardware verification and before success.

1. Production driver exposes a small class with dependency-injected bus/peripheral objects.
2. No debug banners or verbose step-by-step prints remain in normal methods.
3. Keep a private `_self_test()` or minimal public diagnostic method when useful; do not run it by default.
4. `__init__` validates argument types and ranges.
5. `__init__` puts the chip in a known state through reset or explicit configuration confirmation.
6. Public methods raise `ValueError`, `TypeError`, or descriptive `RuntimeError` instead of returning ambiguous sentinel values.
7. Every polling loop has a bounded timeout.
8. Ready/status bits are preferred over fixed sleeps when datasheet provides them.
9. Fixed sleeps include datasheet conversion time plus margin when no ready signal exists.
10. I2C addresses, register constants, masks, commands, and conversion constants are named constants.
11. Read/write helpers include operation context in exceptions.
12. Byte order, signed conversion, scaling, and CRC/checksum rules are explicit.
13. Write-only registers are not read back unless datasheet allows it.
14. Shadow state is updated only after successful hardware writes when possible.
15. `deinit()` enters standby/powerdown when datasheet supports it.
16. No CPython-only modules are required in device code.
17. Avoid dynamic allocation inside hot read loops where practical.
18. Keep comments concise and evidence-oriented, not tutorial prose.
19. `test_<chip>.py` remains separate from production driver.
20. The production file imports only MicroPython-compatible modules.
