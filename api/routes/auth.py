# api/routes/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from config.settings import settings
from api.deps import create_access_token
from models.auth import TokenResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    if form_data.username != settings.ADMIN_USERNAME or form_data.password != settings.ADMIN_PASSWORD:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")
    return TokenResponse(access_token=create_access_token(subject=settings.ADMIN_USERNAME))
