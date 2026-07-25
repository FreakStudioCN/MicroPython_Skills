# maix.fs

Official URL: https://wiki.sipeed.com/maixpy/api/maix/fs.html

Status: seed_reference

Brief: filesystem module.

Stage A policy: use only for README prerequisites and model path checks when the exact API is confirmed by task references. Do not create or download model files.

Common model path convention:

```text
/root/models/<model>.mud
```

Officially indexed callable surface:

```python
from maix import fs

fs.exists(path)
fs.isfile(path)
fs.isdir(path)
fs.getsize(path)
fs.listdir(path, recursive=False, full_path=False)
fs.dirname(path)
fs.basename(path)
fs.abspath(path)
fs.realpath(path)
fs.join([base, name])
fs.open(path, mode)
fs.sync()
```

Indexed but restricted in stage A:

```python
fs.mkdir(path, exist_ok=True, recursive=True)
fs.rmdir(path, recursive=False)
fs.remove(path)
fs.rename(src, dst)
fs.symlink(src, link, force=False)
```

Codegen-safe use:

```python
if not fs.exists(MODEL_PATH):
    print("Missing model:", MODEL_PATH)
```

Restrictions:

- Do not create, remove, rename, or download model/database files.
- Do not use `fs.open(...)` for persistent write flows unless a task-specific reference requires it.
