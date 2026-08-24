import asyncio


class ServoChannel:
    def __init__(self, config, pwm_factory=None, pin_factory=None):
        if pwm_factory is None or pin_factory is None:
            from machine import PWM, Pin

            pwm_factory = PWM
            pin_factory = Pin
        self.config = config
        self.angle = float(config["safe_angle"])
        pin = pin_factory(config["pin"])
        self._pwm = pwm_factory(pin, freq=config.get("frequency_hz", 50))

    def _pulse_us(self, angle):
        minimum_angle = float(self.config.get("min_angle", 0))
        maximum_angle = float(self.config.get("max_angle", 180))
        angle = max(minimum_angle, min(maximum_angle, float(angle)))
        ratio = (angle - minimum_angle) / (maximum_angle - minimum_angle)
        if self.config.get("inverted"):
            ratio = 1.0 - ratio
        return int(self.config["min_us"] + ratio * (self.config["max_us"] - self.config["min_us"]))

    def write(self, angle):
        pulse_us = self._pulse_us(angle)
        if hasattr(self._pwm, "duty_ns"):
            self._pwm.duty_ns(pulse_us * 1000)
        else:
            period_us = 1000000 // int(self.config.get("frequency_hz", 50))
            self._pwm.duty_u16(int(pulse_us * 65535 // period_us))
        self.angle = float(angle)

    def deinit(self):
        self._pwm.deinit()


class ServoController:
    def __init__(self, profile, pwm_factory=None, pin_factory=None):
        self._configs = {item["joint"]: item for item in profile["servos"]}
        self._pwm_factory = pwm_factory
        self._pin_factory = pin_factory
        self._channels = {}
        self._cancel_requested = False

    def start(self):
        if self._channels:
            return
        try:
            for joint in self._configs:
                channel = ServoChannel(self._configs[joint], self._pwm_factory, self._pin_factory)
                self._channels[joint] = channel
                channel.write(self._configs[joint]["safe_angle"])
        except Exception:
            self.deinit()
            raise

    def request_cancel(self):
        self._cancel_requested = True

    def clear_cancel(self):
        self._cancel_requested = False

    def angle(self, joint):
        return self._channels[joint].angle

    async def move(self, joint, target_angle, duration_ms=0):
        if joint not in self._channels:
            raise ValueError("unknown joint: %s" % joint)
        channel = self._channels[joint]
        config = self._configs[joint]
        target = max(float(config.get("min_angle", 0)), min(float(config.get("max_angle", 180)), float(target_angle)))
        delta = abs(target - channel.angle)
        minimum_ms = int(delta * 1000 / float(config["max_speed_deg_s"])) if delta else 0
        duration_ms = max(int(duration_ms), minimum_ms)
        steps = max(1, duration_ms // 20)
        start = channel.angle
        for index in range(1, steps + 1):
            if self._cancel_requested:
                raise asyncio.CancelledError()
            channel.write(start + (target - start) * index / steps)
            if duration_ms:
                await asyncio.sleep_ms(max(1, duration_ms // steps))

    async def move_many(self, targets, duration_ms=0):
        for joint in targets:
            if joint not in self._channels:
                raise ValueError("unknown joint: %s" % joint)
        tasks = [asyncio.create_task(self.move(joint, angle, duration_ms)) for joint, angle in targets.items()]
        for task in tasks:
            await task

    def safe_pose(self):
        for joint, channel in self._channels.items():
            channel.write(self._configs[joint]["safe_angle"])

    def deinit(self):
        for channel in self._channels.values():
            try:
                channel.deinit()
            except Exception:
                pass
        self._channels = {}
