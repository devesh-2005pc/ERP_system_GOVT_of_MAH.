import uuid
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    employee_id: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    must_change_password: bool = False


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class MeResponse(BaseModel):
    id: uuid.UUID
    employee_id: str
    full_name: str
    department_code: str
    department_name: str
    is_department_admin: bool

    class Config:
        from_attributes = True
