import base64
import hashlib
import os
from typing import Optional
from cryptography.fernet import Fernet

class PIICrypto:
    """AES-256 Fernet encryption provider for PII fields stored at rest."""

    _fernet: Optional[Fernet] = None

    @classmethod
    def get_fernet(cls) -> Fernet:
        if cls._fernet is None:
            raw_key = os.getenv("ENCRYPTION_KEY") or os.getenv("APP_SECRET", "sih26094-demo-secret-change-in-production")
            # Derive 32-byte urlsafe base64 key using sha256
            key_digest = hashlib.sha256(raw_key.encode("utf-8")).digest()
            fernet_key = base64.urlsafe_b64encode(key_digest)
            cls._fernet = Fernet(fernet_key)
        return cls._fernet

    @classmethod
    def encrypt(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if not isinstance(value, str):
            value = str(value)
        token = cls.get_fernet().encrypt(value.encode("utf-8"))
        return token.decode("utf-8")

    @classmethod
    def decrypt(cls, ciphertext: Optional[str]) -> Optional[str]:
        if ciphertext is None:
            return None
        try:
            raw = cls.get_fernet().decrypt(ciphertext.encode("utf-8"))
            return raw.decode("utf-8")
        except Exception:
            # Fallback if unencrypted string was present in legacy data
            return ciphertext
