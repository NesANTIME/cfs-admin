import jwt
import uuid
from config.load import CONFIG
from argon2 import PasswordHasher
from datetime import datetime, timedelta, timezone
from config.utils.db import getLongHashPassword, HashDummy
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_ph = PasswordHasher()
long = getLongHashPassword()

_dummy_hash: str | None = None

def get_dummy_hash() -> str:
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = _ph.hash(HashDummy())
    return _dummy_hash

# Compatibilidad backward
def __getattr__(name: str):
    if name == "Dummy_hash":
        return get_dummy_hash()
    raise AttributeError(f"module {__name__} has no attribute {name}")

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

    return jwt.encode(to_encode, CONFIG.Jwt.Secret_key.get_secret_value(), algorithm = CONFIG.Jwt.Algorithm)


def createAccessToken(subject: str | int, extra_claims: dict | None = None) -> str:
    data = {"sub": str(subject)}

    if (extra_claims):
        data.update(extra_claims)

    return createJwtToken(data = data,
        expires_delta = timedelta(minutes = CONFIG.Jwt.Access_token),
        token_type = "access",
    )


def createRefreshToken(subject: str | int) -> str:
    data = {"sub": str(subject)}

    return createJwtToken(data = data,
        expires_delta = timedelta(days=CONFIG.Jwt.Refresh_token),
        token_type = "refresh",
    )


def decodeToken(token: str) -> dict:
    return jwt.decode(
        token, CONFIG.Jwt.Secret_key.get_secret_value(),
        algorithms = [CONFIG.Jwt.Algorithm],
        issuer = ISSUER,
        options = {"require": ["exp", "iat", "sub", "jti", "iss"]},
    )
