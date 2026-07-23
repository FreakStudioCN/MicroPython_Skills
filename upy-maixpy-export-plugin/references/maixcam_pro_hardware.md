# MaixCAM Pro Hardware Reference

Official URL: https://wiki.sipeed.com/hardware/zh/maixcam/maixcam_pro.html

Status: seed_reference

Use this page for hardware-level facts only. Do not infer firmware flashing, MaixHub training, or deployment behavior from this Skill.

Stage A fixed UART bridge:

```text
MaixCAM Pro A19 UART1_TX -> master MCU RX
MaixCAM Pro A18 UART1_RX -> master MCU TX
MaixCAM Pro GND          -> master MCU GND
Baudrate                 -> 115200
Protocol                 -> JSON Lines
```

Safety notes:

- MaixCAM Pro IO is 3.3V. Do not connect directly to 5V UART.
- Prefer UART1 for the generated bridge. Do not prefer UART0 because it may be tied to system logs, maix protocol, or boot behavior.

