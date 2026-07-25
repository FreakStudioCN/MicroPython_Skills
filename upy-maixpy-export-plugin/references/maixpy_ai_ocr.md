# MaixPy OCR Reference

Official URL: https://wiki.sipeed.com/maixpy/doc/zh/vision/ocr.html

API URL: https://wiki.sipeed.com/maixpy/api/maix/nn.html

Status: seed_reference

OCR is supported by official MaixPy `maix.nn.PP_OCR` APIs. Stage A may generate a conservative skeleton, but it must state that OCR model files and language/font/dictionary assets are manual prerequisites.

Required prerequisites:

- OCR model path, for example `/root/models/pp_ocr.mud`.
- Required language/font/dictionary assets for the target MaixPy version.
- User confirmation of the target language and expected output encoding.

Officially indexed API shape:

```python
from maix import nn

ocr = nn.PP_OCR(model="/root/models/pp_ocr.mud")
cam = camera.Camera(ocr.input_width(), ocr.input_height(), ocr.input_format())
objects = ocr.detect(img, thresh=0.3, box_thresh=0.6, char_box=False)
single = ocr.recognize(img, box_points=[])
```

OCR object fields:

```python
obj.box
obj.box.to_list()
obj.box.x1
obj.box.y1
obj.box.x2
obj.box.y2
obj.box.x3
obj.box.y3
obj.box.x4
obj.box.y4
obj.char_str()
obj.char_list()
obj.char_list
obj.idx_list
obj.score
```

Codegen policy:

- May generate a runtime skeleton that emits recognized text as JSONL `label`.
- Must use zero bbox fallback if exact OCR box geometry cannot be read safely.
- Must not claim the OCR model, labels, dictionary, or fonts are installed.
