from app.dependencies import SessionLocal
from app.schemas.users import UserCreate
from app.services.user_service import create_user

db = SessionLocal()

users_to_create = [
    UserCreate(email="demo@jablonsky.ca", first_name="Demo", last_name="User", password="demo1", role="PLATFORM ADMIN"),
    UserCreate(email="demo2@jablonsky.ca", first_name="Demo", last_name="User 2", password="demo2", role="STRUCTURAL DESIGNER"),
]

for u in users_to_create:
    create_user(db, u)
    print(f"Created: {u.email}")

db.close()