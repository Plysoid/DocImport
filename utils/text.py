import re
from datetime import datetime


def norm(s: str) -> str:
    if s is None:
        return ""
    s = str(s).upper()
    # Типові OCR-помилки латинкою у назвах вулиць
    # CUXIBCbKA / CUXIBCBKA = СИХІВСЬКА
    s = s.replace("CUXIBCBKA", "СИХИВСЬКА")
    s = s.replace("CUXIBCЬKA", "СИХИВСЬКА")
    s = s.replace("CUXIBCbKA".upper(), "СИХИВСЬКА")
    trans = str.maketrans({
        "І": "И", "Ї": "И", "I": "И", "Ї": "И", "Є": "Е", "Ґ": "Г", "|": " ",
        "’": "", "'": "", '"': "", ".": " ", ",": " ",
        "-": " ", "/": " ", "\\": " ", "№": " ", ":": " ",
    })
    s = s.translate(trans)
    s = s.replace("ВУЛИЦЯ", "").replace("ВУЛ", "").replace("БУЛЬВАР", "").replace("БУЛ", "")
    s = s.replace("ПРОСПЕКТ", "").replace("ПР", "")
    # У довіднику можуть бути скорочення міст: ДРГ/СТР/СМБ/ІФ.
    # OCR у накладній зазвичай дає повну назву міста.
    s = s.replace("ДРОГОБИЧ", "ДРГ")
    s = s.replace("СТРИЙ", "СТР")
    s = s.replace("САМБИР", "СМБ")
    s = s.replace("ИВАНО ФРАНКИВСК", "ИФ")
    s = s.replace("ИВАНО-ФРАНКИВСК", "ИФ")
    s = re.sub(r"\s+", " ", s).strip()
    # OCR часто дає 86-А як '86 А', а довідник має '86а'.
    # Для адрес це має бути однаковий ключ.
    s = re.sub(r"(\d)\s+([А-ЯA-Z])\b", r"\1\2", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def to_float(v):
    if v is None or v == "": return 0.0
    s = str(v).strip().replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return float(s)
    except Exception:
        return 0.0


def to_date(v):
    if not v:
        return None
    for fmt in ("%d.%m.%Y", "%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(v, fmt).date()
        except Exception:
            pass
    return None
