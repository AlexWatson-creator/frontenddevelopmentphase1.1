from pydantic import BaseModel, ConfigDict, EmailStr, Field
from typing import Optional
from datetime import datetime

# ---------------------------------------------------------------
# you may have to run the uv add "passlib[bcrypt]" command in the terminal to run this code without errors.
# you may also have to run uv add "pydantic[email]" in the terminal too.
# ---------------------------------------------------------------

# Role levels: 0 = Platform Admin, 1 = Office Admin/Partner,
#              2 = BIM Developer/Structural Designer, 3 = standard users
ROLE_LEVEL_MAP: dict[str, int] = {
    "PLATFORM ADMIN":       0,
    "OFFICE ADMIN":         1,
    "PARTNER":              1,
    "BIM DEVELOPER":        2,
    "STRUCTURAL DESIGNER":  2,
    "INSPECTOR":            3,
    "ASSOCIATE":            3,
    "DRAFTER":              3,
    "PROPOSAL":             3,
    "RESEARCH":             3,
    "LEGAL":                3,
}

class UserCreate(BaseModel):
    """Data needed to create a new user."""
    email: EmailStr
    first_name: str = Field(min_length=1)
    last_name: str = Field(min_length=1)
    password: str = Field(min_length=4)
    role: int = Field(default=3)

class UserProjectCreate(BaseModel):
    user_id: int
    project_number: str

class UserUpdate(BaseModel):
    """Fields that can be changed after creation."""
    role: Optional[int] = None
    password: Optional[str] = Field(default=None, min_length=4)
    is_banned: Optional[bool] = None

class UserRead(BaseModel):
    """What gets sent back to the frontend — never includes the password."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    first_name: str
    last_name: str
    role: int
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
