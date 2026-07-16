import os
import json
import secrets
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class SecureBCIGateway:
    def __init__(self, pre_shared_key_hex: str = None):
        if pre_shared_key_hex is None:
            pre_shared_key_hex = os.environ.get("BCI_SHARED_KEY", "")
        if not pre_shared_key_hex:
            raise ValueError(
                "No 256-bit key provided. Set BCI_SHARED_KEY env var or pass pre_shared_key_hex."
            )
        key_bytes = bytes.fromhex(pre_shared_key_hex)
        assert len(key_bytes) == 32, "Requires a 256-bit key (32 bytes)."
        self.aesgcm = AESGCM(key_bytes)

    def encrypt_payload(self, data_dict: dict) -> bytes:
        raw_json_bytes = json.dumps(data_dict).encode('utf-8')
        nonce = secrets.token_bytes(12)
        ciphertext = self.aesgcm.encrypt(nonce, raw_json_bytes, associated_data=None)
        return nonce + ciphertext

    def decrypt_payload(self, encrypted_frame: bytes) -> dict:
        nonce = encrypted_frame[:12]
        ciphertext_with_tag = encrypted_frame[12:]
        decrypted_bytes = self.aesgcm.decrypt(nonce, ciphertext_with_tag, associated_data=None)
        return json.loads(decrypted_bytes.decode('utf-8'))
