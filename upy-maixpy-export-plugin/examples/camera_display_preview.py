# Source: https://wiki.sipeed.com/maixpy/
# Purpose: MaixPy camera + display preview baseline for MaixCAM Pro.
from maix import app, camera, display


cam = camera.Camera(640, 480)
disp = display.Display()

while not app.need_exit():
    img = cam.read()
    disp.show(img)
