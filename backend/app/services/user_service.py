from passlib.context import CryptContext
from sqlalchemy.orm import Session
from app.models.management import User, UserProject, ProjectMeta
from app.schemas.users import UserCreate, UserUpdate, UserRead, UserProjectCreate
from typing import Optional

# ---------------------------------------------------------------
# you may have to run the uv add "passlib[bcrypt]" command in the terminal to run this code without errors.
# you may also have to run uv add "pydantic[email]" in the terminal too.
# ---------------------------------------------------------------

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def create_user(db: Session, data: UserCreate) -> UserRead:
    hashed = pwd_context.hash(data.password)
    user = User(email=data.email, first_name=data.first_name, last_name=data.last_name, password_hash=hashed, role=data.role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserRead.model_validate(user)

def get_users(db: Session) -> list[UserRead]:
    users = db.query(User).all()
    return [UserRead.model_validate(u) for u in users]

def get_user(db: Session, user_id: int) -> Optional[UserRead]:
    user = db.query(User).filter(User.id == user_id).first()
    return UserRead.model_validate(user) if user else None

def update_user(db: Session, user_id: int, data: UserUpdate) -> Optional[UserRead]:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return None
    if data.role is not None:
        user.role = data.role
    if data.is_banned is not None:
        user.is_banned = data.is_banned
    if data.password is not None:
        user.password_hash = pwd_context.hash(data.password)
    db.commit()
    db.refresh(user)
    return UserRead.model_validate(user)

def authenticate_user(db: Session, email: str, password: str) -> Optional[UserRead]:
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return None
    if not pwd_context.verify(password, user.password_hash):
        return None
    return UserRead.model_validate(user)

def create_user_project(db: Session, data: UserProjectCreate) -> list[str]:
    project = db.query(ProjectMeta).filter(ProjectMeta.project_number == data.project_number).first()
    if not project:
        raise ValueError(f"Project '{data.project_number}' does not exist")
    existing = db.query(UserProject).filter(
        UserProject.user_id == data.user_id,
        UserProject.project_number == data.project_number
    ).first()
    if not existing:
        db.add(UserProject(user_id=data.user_id, project_number=data.project_number))
        db.commit()
    return get_user_projects(db, data.user_id)


def get_user_projects(db: Session, user_id: int) -> list[str]:
    rows = db.query(UserProject).filter(UserProject.user_id == user_id).all()
    return [row.project_number for row in rows]

def remove_user_project(db: Session, user_id: int, project_number: str) -> bool:
    row = db.query(UserProject).filter(
        UserProject.user_id == user_id,
        UserProject.project_number == project_number
    ).first()
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True

def delete_user(db: Session, user_id: int) -> bool:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return False
    db.delete(user)
    db.commit()
    return True