from typing import Any

from pydantic import BaseModel


class DebugParticipantResponse(BaseModel):
    total_found: int
    total_returned: int
    data: list[dict[str, Any]]
