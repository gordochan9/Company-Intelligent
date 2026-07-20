from __future__ import annotations

import re
from typing import Any


MAX_IDENTITY_FIELD_LENGTH = 320
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


class OpenWebUIIdentityError(ValueError):
    pass


def normalize_openwebui_identity(headers: dict[str, Any]) -> dict[str, str | None]:
    return {
        "auth_source": "openwebui",
        "user_id": _clean(headers.get("x-openwebui-user-id")),
        "email": _clean(headers.get("x-openwebui-user-email"), required=True),
        "display_name": _clean(headers.get("x-openwebui-user-name")),
        "role_hint": _clean(headers.get("x-openwebui-user-role")),
    }


def _clean(value: Any, *, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise OpenWebUIIdentityError("missing_identity_email")
        return None
    text = str(value).strip()
    if not text:
        if required:
            raise OpenWebUIIdentityError("missing_identity_email")
        return None
    if len(text) > MAX_IDENTITY_FIELD_LENGTH:
        raise OpenWebUIIdentityError("identity_field_too_long")
    if CONTROL_RE.search(text):
        raise OpenWebUIIdentityError("identity_field_invalid")
    return text
