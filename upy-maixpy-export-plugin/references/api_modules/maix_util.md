# maix.util

Official URL: https://wiki.sipeed.com/maixpy/api/maix/util.html

Status: seed_reference

Brief: utility module.

Stage A policy: indexed for completeness. Do not generate utility lifecycle hooks in user code.

Officially indexed callable surface:

```python
from maix import util

util.init_before_main()
util.register_atexit()
util.do_exit_function()
util.str_strip(s)
```

Restrictions:

- Do not generate `init_before_main`, `register_atexit`, or `do_exit_function` in stage A user scripts.
- `str_strip` is not needed for normal JSONL vision output; use Python string methods when needed.
