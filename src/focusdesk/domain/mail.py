"""Installation-level mail metadata. Secrets are deliberately not model fields."""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from .common import new_id


class MailSettings(BaseModel):
    model_config = ConfigDict(extra='forbid', validate_assignment=True)
    provider: Literal['outlook', 'gmail'] = 'outlook'
    profile_id: str = Field(default_factory=new_id)
    address: str = ''
    display_name: str = ''
    remembered: bool = False
    credential_pending_removal: bool = False
