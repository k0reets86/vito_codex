import json

from modules.data_lake import DataLake
from modules.owner_preference_model import OwnerPreferenceModel


def parse_pref_value(raw: str):
    raw = raw.strip()
    if not raw:
        return ""
    if (raw.startswith("{") and raw.endswith("}")) or (raw.startswith("[") and raw.endswith("]")):
        try:
            return json.loads(raw)
        except Exception:
            return raw
    low = raw.lower()
    if low in ("true", "yes", "да", "on"):
        return True
    if low in ("false", "no", "нет", "off"):
        return False
    try:
        if "." in raw:
            return float(raw)
        return int(raw)
    except Exception:
        return raw


def try_set_preference_from_text(text: str) -> bool:
    raw = (text or "").strip()
    if not raw:
        return False
    lower = raw.lower()
    if not (
        lower.startswith("/pref")
        or lower.startswith("pref ")
        or lower.startswith("pref:")
        or lower.startswith("preference:")
        or lower.startswith("предпочтение:")
        or lower.startswith("remember:")
    ):
        return False

    payload = raw
    for prefix in ("/pref", "pref:", "pref ", "preference:", "предпочтение:", "remember:"):
        if lower.startswith(prefix):
            payload = raw[len(prefix):].strip()
            break
    if "=" not in payload:
        return False
    key, value = payload.split("=", 1)
    key = key.strip()
    if not key:
        return False
    value = value.strip()
    if not value:
        return False

    parsed_value = parse_pref_value(value)
    try:
        OwnerPreferenceModel().set_preference(
            key=key,
            value=parsed_value,
            source="owner",
            confidence=1.0,
            notes="explicit owner preference",
        )
        try:
            DataLake().record(
                agent="comms_agent",
                task_type="owner_preference_set",
                status="success",
                output={"key": key, "value": parsed_value},
                source="owner",
            )
        except Exception:
            pass
        return True
    except Exception:
        return False


def try_deactivate_preference_from_text(text: str) -> bool:
    raw = (text or "").strip()
    if not raw:
        return False
    lower = raw.lower()
    prefixes = ("/pref_del", "/pref_remove", "forget ", "забыть ")
    if not any(lower.startswith(p) for p in prefixes):
        return False
    for p in prefixes:
        if lower.startswith(p):
            key = raw[len(p):].strip()
            break
    else:
        key = ""
    if not key:
        return False
    try:
        OwnerPreferenceModel().deactivate_preference(key, notes="owner_request")
        try:
            DataLake().record(
                agent="comms_agent",
                task_type="owner_preference_deactivate",
                status="success",
                output={"key": key},
                source="owner",
            )
        except Exception:
            pass
        return True
    except Exception:
        return False
