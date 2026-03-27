"""
Pydantic schemas for authentication.
"""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    user_id: str = Field(..., min_length=1, description="Unique user identifier")
    password: str = Field(..., min_length=1, description="User password")


class LoginResponse(BaseModel):
    user_id: str
    name: str
    role: str
    token: str
    message: str = "Login successful"
