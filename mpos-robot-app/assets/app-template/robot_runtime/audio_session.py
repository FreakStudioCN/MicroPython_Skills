import asyncio


class AudioSession:
    IDLE = "idle"
    RX = "rx"
    TX = "tx"

    def __init__(self, audio_profile, i2s_factory=None, pin_factory=None):
        if i2s_factory is None or pin_factory is None:
            from machine import I2S, Pin

            i2s_factory = I2S
            pin_factory = Pin
        self.profile = audio_profile
        self._i2s_factory = i2s_factory
        self._pin_factory = pin_factory
        self._i2s = None
        self._state = self.IDLE
        speaker = audio_profile["speaker"]
        self._gain = pin_factory(speaker["gain"], pin_factory.OUT)
        self._shutdown = pin_factory(speaker["shutdown"], pin_factory.OUT)
        self._set_amplifier(False)

    @property
    def state(self):
        return self._state

    def _set_amplifier(self, enabled):
        speaker = self.profile["speaker"]
        self._gain.value(int(speaker.get("gain_level", 0)))
        active = int(speaker.get("shutdown_active_level", 1))
        self._shutdown.value(active if enabled else 1 - active)

    def stop(self):
        self._set_amplifier(False)
        if self._i2s is not None:
            try:
                self._i2s.deinit()
            finally:
                self._i2s = None
        self._state = self.IDLE

    def start_rx(self):
        self.stop()
        microphone = self.profile["microphone"]
        factory = self._i2s_factory
        pin = self._pin_factory
        self._i2s = factory(
            self.profile.get("i2s_id", 0),
            sck=pin(microphone["sck"]),
            ws=pin(microphone["ws"]),
            sd=pin(microphone["sd"]),
            mode=factory.RX,
            bits=self.profile.get("bits", 16),
            format=factory.MONO,
            rate=self.profile.get("sample_rate_hz", 16000),
            ibuf=self.profile.get("ibuf_bytes", 16000),
        )
        self._state = self.RX
        return self._i2s

    def start_tx(self):
        self.stop()
        speaker = self.profile["speaker"]
        factory = self._i2s_factory
        pin = self._pin_factory
        self._i2s = factory(
            self.profile.get("i2s_id", 0),
            sck=pin(speaker["sck"]),
            ws=pin(speaker["ws"]),
            sd=pin(speaker["sd"]),
            mode=factory.TX,
            bits=self.profile.get("bits", 16),
            format=factory.MONO,
            rate=self.profile.get("sample_rate_hz", 16000),
            ibuf=self.profile.get("ibuf_bytes", 16000),
        )
        self._set_amplifier(True)
        self._state = self.TX
        return self._i2s


class I2SMicCodecAdapter:
    def __init__(self, session, chunk_size=640):
        self._session = session
        self._chunk_size = chunk_size
        self._poll = None

    def start(self):
        stream = self._session.start_rx()
        try:
            import select

            self._poll = select.poll()
            self._poll.register(stream, select.POLLIN)
        except Exception:
            self._poll = None

    def any(self):
        if self._session.state != AudioSession.RX:
            return False
        if self._poll is None:
            return True
        return bool(self._poll.poll(0))

    def read(self):
        stream = self._session._i2s
        if stream is None:
            return b""
        buffer = bytearray(self._chunk_size)
        count = stream.readinto(buffer)
        if not count:
            return b""
        return bytes(buffer[:count])

    def clear(self):
        if self._poll is None:
            return
        while self._poll.poll(0):
            if not self.read():
                break

    def stop(self):
        self._poll = None
        self._session.stop()


class I2SSpeakerAdapter:
    def __init__(self, session):
        self._session = session

    def start(self):
        self._session.start_tx()

    async def write(self, chunk):
        stream = self._session._i2s
        if stream is None:
            raise RuntimeError("speaker is not started")
        offset = 0
        while offset < len(chunk):
            written = stream.write(chunk[offset:])
            if written:
                offset += written
            await asyncio.sleep_ms(0)

    def stop(self):
        self._session.stop()
