# Source: https://wiki.sipeed.com/maixpy/doc/en/peripheral/uart.html
# Purpose: UART1 JSON Lines bridge from MaixCAM Pro to a master MCU.
import json
from maix import app, err, pinmap, time, uart


UART_DEVICE = "/dev/ttyS1"
BAUDRATE = 115200
TX_PIN = "A19"
RX_PIN = "A18"
JSONL_FIELDS = ("type", "label", "score", "x", "y", "w", "h")


err.check_raise(pinmap.set_pin_function(TX_PIN, "UART1_TX"), "Failed to set A19 as UART1_TX")
err.check_raise(pinmap.set_pin_function(RX_PIN, "UART1_RX"), "Failed to set A18 as UART1_RX")
serial = uart.UART(UART_DEVICE, BAUDRATE)


def send_result(kind, label, score=1.0, x=0, y=0, w=0, h=0):
    payload = {
        "type": str(kind),
        "label": str(label),
        "score": float(score),
        "x": int(x),
        "y": int(y),
        "w": int(w),
        "h": int(h),
    }
    serial.write_str(json.dumps(payload) + "\n")


while not app.need_exit():
    send_result("status", "ready")
    time.sleep_ms(1000)
