# Source: https://wiki.sipeed.com/maixpy/api/maix/nn.html
# Source: https://wiki.sipeed.com/maixpy/doc/zh/vision/ocr.html
# Purpose: Conservative PP_OCR + UART JSONL skeleton.
#
# Prerequisites:
# - OCR model copied to OCR_MODEL.
# - Language/font/dictionary assets installed for the target MaixPy version.
import json
from maix import app, camera, display, err, fs, image, nn, pinmap, uart


OCR_MODEL = "/root/models/pp_ocr.mud"
OCR_FONT = "/maixapp/share/font/ppocr_keys_v1.ttf"
UART_DEVICE = "/dev/ttyS1"
BAUDRATE = 115200
TX_PIN = "A19"
RX_PIN = "A18"


err.check_raise(pinmap.set_pin_function(TX_PIN, "UART1_TX"), "Failed to set A19 as UART1_TX")
err.check_raise(pinmap.set_pin_function(RX_PIN, "UART1_RX"), "Failed to set A18 as UART1_RX")
serial = uart.UART(UART_DEVICE, BAUDRATE)

if not fs.exists(OCR_MODEL):
    print("OCR model not found; copy the model before running on hardware:", OCR_MODEL)

ocr = nn.PP_OCR(model=OCR_MODEL)
cam = camera.Camera(ocr.input_width(), ocr.input_height(), ocr.input_format())
disp = display.Display()
if fs.exists(OCR_FONT):
    err.check_raise(image.load_font("ppocr", OCR_FONT, size=20), "Failed to load OCR font")
    image.set_default_font("ppocr")


def _value(obj, name, default=0):
    value = getattr(obj, name, default)
    return value() if callable(value) else value


def text_from_ocr(obj):
    char_str = getattr(obj, "char_str", None)
    if callable(char_str):
        return char_str()
    chars = getattr(obj, "char_list", [])
    if callable(chars):
        chars = chars()
    if chars:
        return "".join(str(ch) for ch in chars)
    return str(obj)


def bbox_from_ocr(obj):
    box = getattr(obj, "box", None)
    if box is None:
        return 0, 0, 0, 0
    to_list = getattr(box, "to_list", None)
    if callable(to_list):
        points = to_list()
        if len(points) >= 8:
            xs = [points[0], points[2], points[4], points[6]]
            ys = [points[1], points[3], points[5], points[7]]
            return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
    xs = [_value(box, "x1"), _value(box, "x2"), _value(box, "x3"), _value(box, "x4")]
    ys = [_value(box, "y1"), _value(box, "y2"), _value(box, "y3"), _value(box, "y4")]
    return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)


def send_ocr(text, score=1.0, x=0, y=0, w=0, h=0):
    payload = {
        "type": "ocr",
        "label": str(text),
        "score": float(score),
        "x": int(x),
        "y": int(y),
        "w": int(w),
        "h": int(h),
    }
    serial.write_str(json.dumps(payload) + "\n")


while not app.need_exit():
    img = cam.read()
    objects = ocr.detect(img, thresh=0.3, box_thresh=0.6, char_box=False)
    for obj in objects:
        text = text_from_ocr(obj)
        score = _value(obj, "score", 1.0)
        x, y, w, h = bbox_from_ocr(obj)
        send_ocr(text, score, x, y, w, h)
        img.draw_rect(x, y, w, h, image.COLOR_GREEN)
        img.draw_string(x, y, text, image.COLOR_GREEN)
    disp.show(img)
