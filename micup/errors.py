from typing import Any


class MicupAPIError(Exception):

    def __init__(self, status: int, code: str, message: str, body: Any = None):
        super().__init__(f"HTTP {status} {code}: {message}")
        self.status = status
        self.code = code
        self.message = message
        self.body = body


MicupError = MicupAPIError
