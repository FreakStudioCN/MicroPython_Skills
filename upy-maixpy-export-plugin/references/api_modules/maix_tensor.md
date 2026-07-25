# maix.tensor

Official URL: https://wiki.sipeed.com/maixpy/api/maix/tensor.html

Status: seed_reference

Brief: tensor module.

Stage A policy: reference-only for normal vision exports. Do not generate tensor manipulation unless the user explicitly asks for low-level model I/O and the task reference provides concrete input/output tensor shapes.

Indexed enums/classes:

- `DType`
- `Tensor`
- `Tensors`
- `Vector3f`
- `Vector3i32`
- `Vector3u32`
- `Vector3i16`
- `Vector3u16`

Officially indexed callable surface:

```python
from maix import tensor

tensor.tensor_from_numpy_float32(array, copy=True)
tensor.tensor_from_numpy_uint8(array, copy=True)
tensor.tensor_from_numpy_int8(array, copy=True)
tensor.tensor_to_numpy_float32(t, copy=True)
tensor.tensor_to_numpy_uint8(t, copy=True)
tensor.tensor_to_numpy_int8(t, copy=True)

t = tensor.Tensor(shape, dtype)
t.shape()
t.expand_dims(axis)
t.reshape(shape)
t.flatten()
t.dtype()
t.to_float_list()
t.argmax(axis=65535)
t.argmax1()

items = tensor.Tensors()
items.add_tensor(key, t, copy=True, auto_delete=False)
items.get_tensor(key)
items.keys()
```

Codegen guidance:

- High-level `maix.nn` wrappers such as YOLO, OCR, and FaceRecognizer are preferred over manual tensor handling.
- Generated UART JSONL tasks should not emit raw tensors.
- For AHRS vector inputs, use `tensor.Vector3f(...)` only if an AHRS task is explicitly requested.
