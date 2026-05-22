from pydantic import BaseModel, ConfigDict, EmailStr, Field
from typing import Optional
from datetime import datetime

# ---------------------------------------------------------------
# you may have to run the uv add "passlib[bcrypt]" command in the terminal to run this code without errors.
# you may also have to run uv add "pydantic[email]" in the terminal too.
# ---------------------------------------------------------------

VALID_ROLES = {"PLATFORM ADMIN", "STRUCTURAL DESIGNER", "BIM DEVELOPER", "INSPECTOR", "ASSOCIATE", "DRAFTER", "PROPOSAL", "RESEARCH", "LEGAL", "PARTNER"}

class UserCreate(BaseModel):
    """Data needed to create a new user."""
    email: EmailStr
    first_name: str = Field(min_length=1)
    last_name: str = Field(min_length=1)
    password: str = Field(min_length=4)
    role: str = Field(default="STRUCTURAL DESIGNER")

class UserUpdate(BaseModel):
    """Fields that can be changed after creation."""
    role: Optional[str] = None
    password: Optional[str] = Field(default=None, min_length=4)
    is_banned: Optional[bool] = None

class UserRead(BaseModel):
    """What gets sent back to the frontend — never includes the password."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    first_name: str
    last_name: str
    role: str
    is_banned: bool
    created_at: datetime

class LoginRequest(BaseModel):
    email: str
    password: str



class BulkUploadError(BaseModel):
    row: int
    email: str
    reason: str

class BulkUploadResult(BaseModel):
    created: int
    errors: list[BulkUploadError]