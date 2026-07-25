# maix.err

Official URL: https://wiki.sipeed.com/maixpy/api/maix/err.html

Status: seed_reference

Brief: error code and exception helper module.

Stage A policy: may be used for checked setup calls, especially pinmap/UART setup. Do not build a custom error framework; generated examples should either call `err.check_raise(...)` or use simple `print(...)` diagnostics.

Officially indexed callable surface:

```python
from maix import err

err.to_str(e)
err.get_error()
err.set_error("message")
err.check_raise(result, "message")
err.check_bool_raise(ok, "message")
err.check_null_raise(ptr, "message")
```

Codegen-safe usage:

```python
from maix import err, pinmap

err.check_raise(pinmap.set_pin_function("A19", "UART1_TX"), "Failed to set A19 as UART1_TX")
```

Notes:

- Use `check_raise` only around official calls that return `maix.err.Err`.
- If a task only needs user-visible diagnostics, prefer plain `print(...)` in stage A.
