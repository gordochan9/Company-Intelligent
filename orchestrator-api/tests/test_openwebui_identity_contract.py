from __future__ import annotations

import pytest

from app.services.openwebui_identity import OpenWebUIIdentityError, normalize_openwebui_identity


def test_identity_headers_normalize_to_main_graph_identity_shape() -> None:
    result = normalize_openwebui_identity(
        {
            "x-openwebui-user-id": " user-1 ",
            "x-openwebui-user-email": " admin@demo.com ",
            "x-openwebui-user-name": " Alice ",
            "x-openwebui-user-role": "admin",
        }
    )

    assert result == {
        "auth_source": "openwebui",
        "user_id": "user-1",
        "email": "admin@demo.com",
        "display_name": "Alice",
        "role_hint": "admin",
    }


def test_identity_requires_email() -> None:
    with pytest.raises(OpenWebUIIdentityError):
        normalize_openwebui_identity({})


def test_identity_rejects_control_characters_without_echoing_value() -> None:
    with pytest.raises(OpenWebUIIdentityError) as exc:
        normalize_openwebui_identity({"x-openwebui-user-email": "bad\nuser@example.test"})

    assert str(exc.value) == "identity_field_invalid"


def test_role_hint_does_not_override_email() -> None:
    result = normalize_openwebui_identity(
        {
            "x-openwebui-user-email": "user@demo.com",
            "x-openwebui-user-role": "admin@demo.com",
        }
    )

    assert result["email"] == "user@demo.com"
    assert result["role_hint"] == "admin@demo.com"
