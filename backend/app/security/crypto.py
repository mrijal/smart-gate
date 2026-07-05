import binascii
import os

from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

AES_KEY = os.getenv("AES_KEY", "SmartGateAES256Key!!Nocturnail")
AES_IV = os.getenv("AES_IV", "NocShieldIV16!!")


def decrypt_aes_256_cbc(ciphertext_hex: str, key: bytes = None, iv: bytes = None) -> str:
    if key is None:
        key = AES_KEY.encode("utf-8")
    if iv is None:
        iv = AES_IV.encode("utf-8")

    ciphertext = binascii.unhexlify(ciphertext_hex)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    plaintext_padded = cipher.decrypt(ciphertext)
    plaintext = unpad(plaintext_padded, AES.block_size)
    return plaintext.decode("utf-8")


def is_encrypted_payload(payload: str) -> bool:
    if len(payload) < 32:
        return False
    try:
        bytes.fromhex(payload)
        return True
    except ValueError:
        return False
