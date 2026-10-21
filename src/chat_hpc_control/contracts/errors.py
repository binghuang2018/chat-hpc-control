"""Stable public errors, separate from native computation failure states."""


class ControlError(ValueError):
    def __init__(self, code: str, message: str, *, retryable: bool = False,
                 evidence_refs: list[str] | None = None):
        self.code = code
        self.message = message
        self.retryable = retryable
        self.evidence_refs = evidence_refs or []
        super().__init__(f"{code}: {message}")

    def to_dict(self):
        return {"code": self.code, "message": self.message,
                "retryable": self.retryable, "evidence_refs": self.evidence_refs}
