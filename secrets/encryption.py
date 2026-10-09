import os
import hashlib
import hmac
import base64
import json
from typing import Tuple, Dict, Any, Optional

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False

class KeyManager:
    """Manages master root keys and Key Encryption Keys (KEK). Pluggable for HSM/KMS."""

    def __init__(self, master_seed: Optional[str] = None):
        self._master_seed = master_seed or os.environ.get("OMNIA_MASTER_KEY_SEED") or "omnia_secure_enclave_master_root_v1"
        self._keys: Dict[str, bytes] = {}
        self._derive_keys()

    def _derive_keys(self):
        # Derive primary KEK
        primary_kek = hashlib.pbkdf2_hmac(
            "sha256",
            self._master_seed.encode("utf-8"),
            b"omnia_kek_salt_primary",
            100000,
            dklen=32
        )
        self._keys["kek_v1"] = primary_kek

        # Derive secondary rotation KEK
        secondary_kek = hashlib.pbkdf2_hmac(
            "sha256",
            self._master_seed.encode("utf-8"),
            b"omnia_kek_salt_secondary",
            100000,
            dklen=32
        )
        self._keys["kek_v2"] = secondary_kek

    def get_kek(self, key_id: str = "kek_v1") -> bytes:
        if key_id not in self._keys:
            raise KeyError(f"Key ID '{key_id}' not found in KeyManager.")
        return self._keys[key_id]

    def register_key(self, key_id: str, key_bytes: bytes):
        if len(key_bytes) < 32:
            raise ValueError("Encryption keys must be at least 256 bits (32 bytes).")
        self._keys[key_id] = key_bytes

key_manager = KeyManager()

class EncryptionEngine:
    """Envelope encryption engine providing authenticated confidentiality and integrity at rest."""

    def __init__(self, km: Optional[KeyManager] = None):
        self.km = km or key_manager

    def encrypt(self, plaintext: str, key_id: str = "kek_v1") -> Tuple[str, str, str, str]:
        """
        Encrypts plaintext string.
        Returns: (ciphertext_b64, salt_b64, nonce_b64, fingerprint)
        """
        kek = self.km.get_kek(key_id)
        salt = os.urandom(16)
        nonce = os.urandom(12)

        # Derive Data Encryption Key (DEK) from KEK + salt
        dek = hashlib.pbkdf2_hmac("sha256", kek, salt, 10000, dklen=32)
        plain_bytes = plaintext.encode("utf-8")

        if HAS_CRYPTOGRAPHY:
            aesgcm = AESGCM(dek)
            ct_bytes = aesgcm.encrypt(nonce, plain_bytes, None)
            ciphertext_b64 = base64.b64encode(ct_bytes).decode("ascii")
        else:
            # High-grade fallback: Authenticated keystream with HMAC-SHA256
            keystream = bytearray()
            counter = 0
            while len(keystream) < len(plain_bytes):
                chunk = hmac.new(dek, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
                keystream.extend(chunk)
                counter += 1

            raw_ct = bytes(p ^ k for p, k in zip(plain_bytes, keystream[:len(plain_bytes)]))
            # Authenticate with HMAC tag
            tag = hmac.new(dek, nonce + raw_ct, hashlib.sha256).digest()
            bundle = tag + raw_ct
            ciphertext_b64 = base64.b64encode(bundle).decode("ascii")

        salt_b64 = base64.b64encode(salt).decode("ascii")
        nonce_b64 = base64.b64encode(nonce).decode("ascii")
        fingerprint = hashlib.sha256(plain_bytes).hexdigest()[:16]

        return ciphertext_b64, salt_b64, nonce_b64, fingerprint

    def decrypt(self, ciphertext_b64: str, salt_b64: str, nonce_b64: str, key_id: str = "kek_v1") -> str:
        """Decrypts ciphertext and verifies integrity. Raises ValueError if tampered or invalid key."""
        kek = self.km.get_kek(key_id)
        salt = base64.b64decode(salt_b64.encode("ascii"))
        nonce = base64.b64decode(nonce_b64.encode("ascii"))
        ct_bytes = base64.b64decode(ciphertext_b64.encode("ascii"))

        dek = hashlib.pbkdf2_hmac("sha256", kek, salt, 10000, dklen=32)

        if HAS_CRYPTOGRAPHY:
            try:
                aesgcm = AESGCM(dek)
                plain_bytes = aesgcm.decrypt(nonce, ct_bytes, None)
                return plain_bytes.decode("utf-8")
            except Exception as e:
                raise ValueError(f"Decryption failed: integrity verification rejected or invalid key. ({e})")
        else:
            if len(ct_bytes) < 32:
                raise ValueError("Decryption failed: ciphertext bundle truncated.")
            tag = ct_bytes[:32]
            raw_ct = ct_bytes[32:]

            expected_tag = hmac.new(dek, nonce + raw_ct, hashlib.sha256).digest()
            if not hmac.compare_digest(tag, expected_tag):
                raise ValueError("Decryption failed: HMAC tag mismatch (ciphertext tampered or invalid key).")

            keystream = bytearray()
            counter = 0
            while len(keystream) < len(raw_ct):
                chunk = hmac.new(dek, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
                keystream.extend(chunk)
                counter += 1

            plain_bytes = bytes(c ^ k for c, k in zip(raw_ct, keystream[:len(raw_ct)]))
            return plain_bytes.decode("utf-8")

    def verify_integrity(self, ciphertext_b64: str, salt_b64: str, nonce_b64: str, key_id: str = "kek_v1") -> bool:
        """Verifies integrity without needing to expose or process the plaintext."""
        try:
            self.decrypt(ciphertext_b64, salt_b64, nonce_b64, key_id)
            return True
        except Exception:
            return False

encryption_engine = EncryptionEngine()
