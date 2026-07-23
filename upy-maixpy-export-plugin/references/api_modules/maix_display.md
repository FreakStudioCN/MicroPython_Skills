# maix.display

Official URL: https://wiki.sipeed.com/maixpy/api/maix/display.html

Status: seed_reference

Brief: control display device and show image on it.

Stage A policy: may be used for preview/debug display.

Known safe surface:

```python
from maix import display
disp = display.Display()
disp.show(img)
```

Screen replacement, MaixVision display routing, and touch UI details require task-specific references.
