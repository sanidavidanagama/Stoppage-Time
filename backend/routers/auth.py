from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from backend.auth import create_access_token
from backend.config import backend_settings

router = APIRouter(tags=["auth"])


@router.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    if (
        form_data.username != backend_settings.ADMIN_USERNAME
        or form_data.password != backend_settings.ADMIN_PASSWORD
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(sub=form_data.username)
    return {"access_token": token, "token_type": "bearer"}
