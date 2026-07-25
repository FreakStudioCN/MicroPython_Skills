# maix.example

Official URL: https://wiki.sipeed.com/maixpy/api/maix/example.html

Status: seed_reference

Brief: example module.

Stage A policy: example/source index only. Prefer files under `examples/` in this Skill for generation references.

Officially indexed callable surface includes synthetic examples such as:

```python
from maix import example

example.hello(name)
example.callback(cb)
example.hello_dict(data)
```

Restrictions:

- Do not import `maix.example` in generated user applications.
- Use this file only to verify how MaixPy documents Python bindings, callback signatures, and generated API pages.
