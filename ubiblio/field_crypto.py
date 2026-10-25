import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from .vars import SECRET_KEY

PREFIX = "enc1:"
ENCRYPTED_USER_FIELDS = (
    "givenName",
    "surname1",
    "surname2",
    "province",
    "canton",
    "district",
    "address",
    "phone",
    "email",
)


def _fernet() -> Fernet:
    digest = hashlib.sha256(SECRET_KEY.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def is_ciphertext(value) -> bool:
    return isinstance(value, str) and value.startswith(PREFIX)


def encrypt_value(value: str) -> str:
    token = _fernet().encrypt(value.encode("utf-8")).decode("ascii")
    return PREFIX + token


def decrypt_value(value: str) -> str:
    if not is_ciphertext(value):
        return value
    try:
        return _fernet().decrypt(value[len(PREFIX):].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""
