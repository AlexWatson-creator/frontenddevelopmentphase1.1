from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.dependencies import get_db
from app.schemas.users import UserCreate, UserUpdate, UserRead, LoginRequest
from app.services import user_service
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from openpyxl import load_workbook
from io import BytesIO
from app.schemas.users import UserCreate, UserUpdate, UserRead, LoginRequest, BulkUploadResult, BulkUploadError, VALID_ROLES

router = APIRouter(tags=["Users"])

@router.get("/users", response_model=list[UserRead])
def list_users(db: Session = Depends(get_db)):
    return user_service.get_users(db)

@router.post("/users", response_model=UserRead, status_code=201)
def create_user(data: UserCreate, db: Session = Depends(get_db)):
    return user_service.create_user(db, data)



@router.post("/users/bulk-upload", response_model=BulkUploadResult)
def bulk_upload_users(file: UploadFile = File(...), db: Session = Depends(get_db)):
    contents = file.file.read()
    wb = load_workbook(filename=BytesIO(contents))
    ws = wb.active

    headers = [cell.value for cell in ws[1]]
    required = {"email", "first_name", "last_name", "password", "role"}
    if not required.issubset(set(headers)):
        raise HTTPException(status_code=400, detail=f"Missing columns. Required: {required}")

    created_count = 0
    errors = []
    rows = list(ws.iter_rows(min_row=2, values_only=True))

    users_by_email = {}

    for i, raw_row in enumerate(rows, start=2):
        data = dict(zip(headers, raw_row))
        email = str(data.get("email") or "").strip()
        role = str(data.get("role") or "STRUCTURAL DESIGNER").strip()

        if email not in users_by_email:
            users_by_email[email] = {"data": data, "roles": [role], "row": i}
        else:
            users_by_email[email]["roles"].append(role)

    for email, info in users_by_email.items():
        data = info["data"]
        roles = info["roles"]
        row_idx = info["row"]
        try:
            for role in roles:
                if role not in VALID_ROLES:
                    raise ValueError(f"Invalid role '{role}'")
                
            user_data = UserCreate(
                email=email,
                first_name=str(data.get("first_name") or "").strip(),
                last_name=str(data.get("last_name") or "").strip(),
                password=str(data.get("password") or "").strip(),
                role=roles[0],
            )
            user_service.create_user(db, user_data)
            created_count += 1
        except Exception as e:
            errors.append(BulkUploadError(row=row_idx, email=email, reason=str(e)))

    return BulkUploadResult(created=created_count, errors=errors)

@router.patch("/users/{user_id}", response_model=UserRead)
def update_user(user_id: int, data: UserUpdate, db: Session = Depends(get_db)):
    result = user_service.update_user(db, user_id, data)
    if result is None:
        raise HTTPException(status_code=404, detail="User not found")
    return result



@router.post("/auth/login", response_model=UserRead)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = user_service.authenticate_user(db, data.email, data.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if user.is_banned:
        raise HTTPException(status_code=403, detail="This account has been suspended")
    return user