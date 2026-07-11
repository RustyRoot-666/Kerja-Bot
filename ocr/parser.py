from __future__ import annotations

import re
from dataclasses import dataclass


VENDORS = {
    "HUAWEI": "Huawei",
    "ZTE": "ZTE",
    "FIBERHOME": "Fiberhome",
    "NOKIA": "Nokia",
    "ALCATEL": "Nokia",
    "RAISECOM": "Raisecom",
    "FIBERLINK": "Fiberlink",
}

MODEL_PATTERNS = [
    r"\bHG8145V5\b",
    r"\bHG8245H\b",
    r"\bHG8245[A-Z0-9-]*\b",
    r"\bEG8145V5\b",
    r"\bZXHN\s*[A-Z0-9-]+\b",
    r"\bF609\b",
    r"\bF670L\b",
    r"\bF670Y\b",
    r"\bF670\b",
    r"\bF6600P\b",
    r"\bF660\b",
    r"\bAN5506[A-Z0-9-]*\b",
    r"\bG-?[0-9]{3,4}[A-Z0-9-]*\b",
    r"\bISCOM[A-Z0-9-]*\b",
]

SERIAL_LABEL_PATTERNS = [
    r"(?:GPON\s*SN|PON\s*NO|PON\s*NUMBER|SERIAL\s*NUMBER|S/N|SN)\s*[:：#-]?\s*([A-Z0-9]{8,24})",
    r"(?:GPONSN|PONNO)\s*[:：#-]?\s*([A-Z0-9]{8,24})",
]

PON_SERIAL_LABEL_PATTERNS = [
    r"(?:PON\s*NO|PON\s*NUMBER|PONNO)\s*[:#-]?\s*([A-Z0-9]{8,24})",
]

GPON_SERIAL_LABEL_PATTERNS = [
    r"(?:GPON\s*SN|GPONSN)\s*[:#-]?\s*([A-Z0-9]{8,24})",
]

GENERAL_SERIAL_LABEL_PATTERNS = [
    r"(?:SERIAL\s*NUMBER|S/N|SN)\s*[:#-]?\s*([A-Z0-9]{8,24})",
]

FALLBACK_SERIAL_PATTERNS = [
    r"\b48575443[A-Z0-9]{8}\b",
    r"\bHWTC[A-Z0-9]{8,16}\b",
    r"\bZTEG[A-Z0-9]{8,16}\b",
    r"\bFHTT[A-Z0-9]{8,16}\b",
    r"\bALCL[A-Z0-9]{8,16}\b",
    r"\bRCOM[A-Z0-9]{8,16}\b",
    r"\b[A-Z]{4}[A-Z0-9]{8,16}\b",
]


@dataclass(frozen=True)
class ParsedOntLabel:
    serial_number: str | None
    model: str | None
    manufacturer: str | None
    confidence: float
    raw_text: str


def normalize_text(raw_text: str) -> str:
    text = raw_text.upper()
    replacements = {
        "PON N0": "PON NO",
        "PONNO": "PON NO",
        "GPONSN": "GPON SN",
        "SERIAL NO": "SERIAL NUMBER",
        "S / N": "S/N",
        "O": "0",
    }
    for old, new in replacements.items():
        if old in {"O"}:
            continue
        text = text.replace(old, new)
    text = re.sub(r"[^A-Z0-9/:：#\-\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def clean_serial(serial: str) -> str:
    serial = serial.upper().strip()
    serial = serial.replace(" ", "").replace("-", "").replace(":", "")
    return serial


def clean_huawei_pon(serial: str) -> str:
    serial = clean_serial(serial)
    return serial.translate(str.maketrans({"I": "1", "L": "1", "O": "0", "G": "6"}))


def normalize_huawei_pon(serial: str) -> str | None:
    serial = clean_huawei_pon(serial)
    if serial.startswith("5443"):
        serial = f"4857{serial}"
    if re.fullmatch(r"48575443[0-9A-F]{8}", serial):
        return serial
    return None


def parse_ont_label(raw_text: str, average_confidence: float) -> ParsedOntLabel:
    text = normalize_text(raw_text)
    serial = find_serial(text)
    model = find_model(text)
    vendor = find_vendor(text, serial, model)

    score = max(0.0, min(1.0, average_confidence))
    if serial:
        score += 0.15
    if model:
        score += 0.10
    if vendor:
        score += 0.05
    if serial and is_suspicious_huawei_pon(serial):
        score = min(score, 0.40)
    score = max(0.0, min(1.0, score))

    return ParsedOntLabel(
        serial_number=serial,
        model=model,
        manufacturer=vendor,
        confidence=score,
        raw_text=raw_text,
    )


def find_serial(text: str) -> str | None:
    # Huawei labels can show both "(S)SN" and "PON No". For IndiHome ONT
    # replacement, PON No is the value technicians need as SN ONT.
    for pattern in PON_SERIAL_LABEL_PATTERNS:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            serial = normalize_huawei_pon(match.group(1)) or clean_serial(match.group(1))
            if is_valid_serial(serial):
                return serial

    for pattern in GPON_SERIAL_LABEL_PATTERNS:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            serial = clean_serial(match.group(1))
            if is_valid_serial(serial):
                return serial

    huawei_pon = find_huawei_pon_fallback(text)
    if huawei_pon:
        return huawei_pon

    for pattern in GENERAL_SERIAL_LABEL_PATTERNS:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            serial = clean_serial(match.group(1))
            if is_valid_serial(serial):
                return serial

    compact = text.replace(" ", "")
    for pattern in FALLBACK_SERIAL_PATTERNS:
        match = re.search(pattern, compact, flags=re.IGNORECASE)
        if match:
            serial = clean_serial(match.group(0))
            if is_valid_serial(serial):
                return serial
    return None


def find_huawei_pon_fallback(text: str) -> str | None:
    compact = text.upper().replace(" ", "")
    compact = compact.replace("\n", "")
    patterns = [
        r"48575443[0-9A-FILO]{8}",
        r"5443[0-9A-FILO]{8}",
    ]
    for pattern in patterns:
        match = re.search(pattern, compact)
        if not match:
            continue
        serial = normalize_huawei_pon(match.group(0))
        if serial:
            return serial
    return None


def find_model(text: str) -> str | None:
    for pattern in MODEL_PATTERNS:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return re.sub(r"\s+", "", match.group(0).upper())
    return None


def find_vendor(text: str, serial: str | None, model: str | None) -> str | None:
    for key, name in VENDORS.items():
        if key in text:
            return name
    if serial:
        prefix = serial[:4]
        return {
            "HWTC": "Huawei",
            "4857": "Huawei",
            "ZTEG": "ZTE",
            "FHTT": "Fiberhome",
            "ALCL": "Nokia",
            "RCOM": "Raisecom",
        }.get(prefix)
    if model:
        if model.startswith(("HG", "EG")):
            return "Huawei"
        if model.startswith(("ZXHN", "F6")):
            return "ZTE"
        if model.startswith("AN5506"):
            return "Fiberhome"
    return None


def is_valid_serial(serial: str) -> bool:
    return 8 <= len(serial) <= 24 and bool(re.fullmatch(r"[A-Z0-9]+", serial))


def is_suspicious_huawei_pon(serial: str) -> bool:
    if not serial.startswith("48575443") or len(serial) != 16:
        return False
    suffix = serial[8:]
    return suffix.isdigit()
