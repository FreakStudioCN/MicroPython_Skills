import asyncio


class ConversationOrchestrator:
    IDLE = "idle"
    LISTENING = "listening"
    ASR = "asr"
    THINKING = "thinking"
    SPEAKING_AND_ACTING = "speaking_and_acting"
    COOLDOWN = "cooldown"
    ERROR = "error"

    def __init__(self, asr, llm, tts, mic, speaker, actions):
        self.asr = asr
        self.llm = llm
        self.tts = tts
        self.mic = mic
        self.speaker = speaker
        self.actions = actions
        self.state = self.IDLE
        self._cancel_requested = False

    def request_cancel(self):
        self._cancel_requested = True
        self.actions.request_cancel()

    async def run_once(self, context, confirmed=False):
        self._cancel_requested = False
        self.actions.clear_cancel()
        try:
            self.state = self.LISTENING
            self.mic.start()
            self.state = self.ASR
            text = await self.asr.recognize_mic(self.mic)
            self.mic.stop()
            if self._cancel_requested:
                raise asyncio.CancelledError()
            if not text:
                self.state = self.IDLE
                return {"status": "no_speech", "text": ""}
            self.state = self.THINKING
            response = await self.llm.complete(context, text)
            response = self.actions.validate(response)
            if self._cancel_requested:
                raise asyncio.CancelledError()
            self.state = self.SPEAKING_AND_ACTING
            self.speaker.start()
            tts_task = asyncio.create_task(self.tts.synthesize_streaming(response.get("reply_text", ""), self.speaker.write))
            action_task = asyncio.create_task(self.actions.execute(response, confirmed=confirmed))
            await tts_task
            self.speaker.stop()
            action_result = await action_task
            self.state = self.COOLDOWN
            await asyncio.sleep_ms(100)
            self.state = self.IDLE
            return {"status": "completed", "text": text, "response": response, "actions": action_result}
        except asyncio.CancelledError:
            self.mic.stop()
            self.speaker.stop()
            self.state = self.IDLE
            return {"status": "cancelled"}
        except Exception:
            self.mic.stop()
            self.speaker.stop()
            self.state = self.ERROR
            raise
