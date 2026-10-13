from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass


@dataclass
class Step:
    stage: str
    message: str
    current: int | None = None
    total: int | None = None
    folder: str | None = None

    def __str__(self) -> str:
        return self.message

    def to_json(self) -> str:
        fields = {key: value for key, value in asdict(self).items() if value is not None}
        return json.dumps(fields, ensure_ascii=False)


Progress = Callable[[Step], None]
