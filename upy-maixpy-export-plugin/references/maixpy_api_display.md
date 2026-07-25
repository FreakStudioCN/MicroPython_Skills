# MaixPy Display Reference

Official URL: https://wiki.sipeed.com/maixpy/api/maix/display.html

Task doc: https://wiki.sipeed.com/maixpy/doc/en/vision/display.html

Status: seed_reference

Known safe shape from MaixPy examples:

```python
from maix import display

disp = display.Display()
disp.show(img)
```

Use only with an image returned by camera or image APIs.

MaixVision debug display is indexed as:

```python
from maix import display
display.send_to_maixvision(img)
```

Stage A should keep local device display preview as the default and mention MaixVision as manual IDE/debug tooling.
