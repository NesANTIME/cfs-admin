import jwt
import uuid
from config.config import CONFIG
from argon2 import PasswordHasher
from datetime import datetime, timedelta, timezone
from config.config import getLongHashPassword, HashDummy
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_ph = PasswordHasher()
long = getLongHashPassword()

Dummy_hash = _ph.hash(HashDummy())
ISSUER = "cfs-admin-api"


def hashearPassword(password: str) -> str:
    if (len(password) < long):
        raise ValueError(f"La contraseña debe tener al menos {long} caracteres.")
    
    return _ph.hash(password)

def rehashearPassword(password: str) -> str:
    return _ph.hash(password)


def verifyPassword(hashSave: str, password: str) -> bool:
    try:
        return _ph.verify(hashSave, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def requireReHash(hashSave: str) -> bool:
    return _ph.check_needs_rehash(hashSave)



# ---



def createJwtToken(data: dict, expires_delta: timedelta, token_type: str = "access") -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + expires_delta

    to_encode.update({
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "type": token_type,
        "jti": uuid.uuid4().hex,
        "iss": ISSUER,
    })

    return jwt.encode(to_encode, CONFIG.jwt_secret_key, algorithm = CONFIG.jwt_algorithm)


def createAccessToken(subject: str | int, extra_claims: dict | None = None) -> str:
    data = {"sub": str(subject)}

    if (extra_claims):
        data.update(extra_claims)

    return createJwtToken(data = data,
        expires_delta = timedelta(minutes = CONFIG.jwt_access_token_expire_minutes),
        token_type = "access",
    )


def createRefreshToken(subject: str | int) -> str:
    data = {"sub": str(subject)}

    return createJwtToken(data = data,
        expires_delta = timedelta(days=CONFIG.jwt_refresh_token_expire_days),
        token_type = "refresh",
    )


def decodeToken(token: str) -> dict:
    return jwt.decode(
        token, CONFIG.jwt_secret_key,
        algorithms = [CONFIG.jwt_algorithm],
        issuer = ISSUER,
        options = {"require": ["exp", "iat", "sub", "jti", "iss"]},
    )
