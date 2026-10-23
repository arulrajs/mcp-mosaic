"""
Sensitive data detectors for Mist network data.
Each entry: (type_label, compiled_pattern, group_index)
group_index=0 means replace full match; >0 means replace only that capture group.
"""
import re
from typing import NamedTuple


class Detector(NamedTuple):
    label: str
    pattern: re.Pattern
    group: int = 0  # 0 = full match, n = nth capture group


# Order matters: more specific patterns first to avoid partial overlaps.
DETECTORS: list[Detector] = [
    # Mist API token (Token <hex>) and Bearer tokens
    Detector("KEY", re.compile(
        r'\b(?:Token\s+[0-9a-fA-F]{32,}|Bearer\s+[A-Za-z0-9\-._~+/]+=*)',
        re.IGNORECASE
    )),
    # JWT
    Detector("JWT", re.compile(
        r'\beyJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+'
    )),
    # UUID (org_id, site_id, device_id) — 8-4-4-4-12
    Detector("UID", re.compile(
        r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b',
        re.IGNORECASE
    )),
    # MAC address
    Detector("MAC", re.compile(
        r'\b([0-9a-fA-F]{2}[:\-]){5}[0-9a-fA-F]{2}\b'
    )),
    # IPv4
    Detector("IP", re.compile(
        r'\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b'
    )),
    # Internal hostnames (.internal, .corp, .local, .lan)
    Detector("HOST", re.compile(
        r'\b[a-zA-Z0-9](?:[a-zA-Z0-9\-]*[a-zA-Z0-9])?'
        r'\.(?:internal|corp|local|lan)\b',
        re.IGNORECASE
    )),
    # JSON credential fields: "password":"val", "secret":"val", "token":"val"
    # group=1 captures only the value; surrounding JSON structure is preserved.
    Detector("CRED", re.compile(
        r'"(?:password|passwd|secret|token|api_key|apikey|auth|psk|passphrase|'
        r'private_key|client_secret)"\s*:\s*"([^"]{4,})"',
        re.IGNORECASE
    ), group=1),
    # Email
    Detector("EMAIL", re.compile(
        r'\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b'
    )),
]
