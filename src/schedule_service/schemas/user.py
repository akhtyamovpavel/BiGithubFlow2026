"""Account and session API schemas."""

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from schedule_service.models.user import UserRole


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: SecretStr


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=100, pattern=r"^\S+$")
    password: SecretStr = Field(min_length=8, max_length=128)
    role: UserRole


class UserUpdate(BaseModel):
    role: UserRole | None = None
    is_active: bool | None = None


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: UserRole
    is_active: bool


class TokenRead(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
