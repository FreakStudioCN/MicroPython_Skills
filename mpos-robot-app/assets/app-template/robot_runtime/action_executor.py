import asyncio


class ActionValidationError(ValueError):
    pass


class ActionExecutor:
    def __init__(self, servos, poses=None, max_actions=12, max_wait_ms=5000):
        self.servos = servos
        self.poses = poses or {}
        self.max_actions = max_actions
        self.max_wait_ms = max_wait_ms
        self._completed = []
        self._cancel_requested = False

    def request_cancel(self):
        self._cancel_requested = True
        self.servos.request_cancel()

    def clear_cancel(self):
        self._cancel_requested = False
        self.servos.clear_cancel()

    def validate(self, response):
        if not isinstance(response, dict):
            raise ActionValidationError("LLM response must be an object")
        allowed_response = {"operation_id", "reply_text", "emotion", "requires_confirmation", "actions"}
        unknown = set(response).difference(allowed_response)
        if unknown:
            raise ActionValidationError("unknown response fields: %s" % sorted(unknown))
        operation_id = response.get("operation_id")
        if not isinstance(operation_id, str) or not operation_id:
            raise ActionValidationError("operation_id is required")
        actions = response.get("actions")
        if not isinstance(actions, list) or len(actions) > self.max_actions:
            raise ActionValidationError("actions must be a bounded list")
        for action in actions:
            self._validate_action(action)
        if not isinstance(response.get("reply_text", ""), str):
            raise ActionValidationError("reply_text must be a string")
        if not isinstance(response.get("requires_confirmation", False), bool):
            raise ActionValidationError("requires_confirmation must be boolean")
        return response

    def _validate_action(self, action):
        if not isinstance(action, dict):
            raise ActionValidationError("action must be an object")
        action_type = action.get("type")
        if action_type == "move_joint":
            allowed = {"type", "joint", "angle", "duration_ms"}
            if set(action).difference(allowed):
                raise ActionValidationError("move_joint contains unsupported fields")
            if action.get("joint") not in self.servos._configs:
                raise ActionValidationError("unknown joint")
            if not isinstance(action.get("angle"), (int, float)) or isinstance(action.get("angle"), bool):
                raise ActionValidationError("angle must be numeric")
        elif action_type == "pose":
            allowed = {"type", "name", "duration_ms"}
            if set(action).difference(allowed) or action.get("name") not in self.poses:
                raise ActionValidationError("unknown or invalid pose")
        elif action_type == "wait":
            allowed = {"type", "duration_ms"}
            duration = action.get("duration_ms")
            if set(action).difference(allowed) or not isinstance(duration, int) or isinstance(duration, bool) or not 0 <= duration <= self.max_wait_ms:
                raise ActionValidationError("invalid wait action")
        else:
            raise ActionValidationError("unsupported action type")
        duration = action.get("duration_ms", 0)
        if not isinstance(duration, int) or isinstance(duration, bool) or duration < 0 or duration > 15000:
            raise ActionValidationError("invalid duration_ms")

    async def execute(self, response, confirmed=False):
        response = self.validate(response)
        operation_id = response["operation_id"]
        if operation_id in self._completed:
            return {"operation_id": operation_id, "status": "already_completed", "actions_completed": 0}
        if response.get("requires_confirmation") and not confirmed:
            return {"operation_id": operation_id, "status": "confirmation_required", "actions_completed": 0}
        completed = 0
        for action in response["actions"]:
            if self._cancel_requested:
                raise asyncio.CancelledError()
            if action["type"] == "move_joint":
                await self.servos.move(action["joint"], action["angle"], action.get("duration_ms", 0))
            elif action["type"] == "pose":
                await self.servos.move_many(self.poses[action["name"]], action.get("duration_ms", 0))
            else:
                await asyncio.sleep_ms(action["duration_ms"])
            completed += 1
        self._completed.append(operation_id)
        if len(self._completed) > 32:
            self._completed.pop(0)
        return {"operation_id": operation_id, "status": "completed", "actions_completed": completed}
