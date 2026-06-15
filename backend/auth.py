from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from backend.config import backend_settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def create_access_token(sub: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=backend_settings.JWT_EXPIRE_DAYS)
    return jwt.encode(
        {"sub": sub, "exp": expire},
        backend_settings.JWT_SECRET_KEY,
        algorithm=backend_settings.JWT_ALGORITHM,
    )


def verify_token(token: str) -> str:
    try:
        payload = jwt.decode(
            token,
            backend_settings.JWT_SECRET_KEY,
            algorithms=[backend_settings.JWT_ALGORITHM],
        )
        sub: str = payload.get("sub")
        if sub is None:
            raise _credentials_error()
        return sub
    except JWTError:
        raise _credentials_error()


def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    return verify_token(token)


def _credentials_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
