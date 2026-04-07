from pydantic import BaseModel


class AuthMeResponse(BaseModel):
    auth_enabled: bool
    email: str | None = None
    display_name: str | None = None
    role: str | None = None
