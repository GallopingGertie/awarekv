import hashlib


def compute_checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_checksum(data: bytes, expected: str) -> bool:
    actual = compute_checksum(data)
    return actual == expected
