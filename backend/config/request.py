from pydantic import BaseModel, Field

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int

class LoginRequest(BaseModel):
    username: str = Field(..., min_length = 3, max_length = 50)
    password: str = Field(..., min_length = 1, max_length = 128)

class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., max_length = 2048)
