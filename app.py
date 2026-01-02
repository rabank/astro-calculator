# app.py
import json, traceback
from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import swisseph as swe
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# ---- Swiss Ephemeris: път до ефемеридите ----
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EPHE_PATH = os.path.join(BASE_DIR, "ephe")  # папка "ephe" до app.py
swe.set_ephe_path(EPHE_PATH)

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=False)

# ---------- конфигурация през ENV ----------
# Ако не са сетнати: LAHIRI + MEAN NODE
AYAN = os.getenv("AYANAMSHA", "LAHIRI").upper()   # LAHIRI | RAMAN | KP
NODE = os.getenv("NODE_TYPE", "MEAN").upper()     # TRUE | MEAN

AYAN_MAP = {
    "LAHIRI": swe.SIDM_LAHIRI,          # Chitrapaksha
    "RAMAN":  swe.SIDM_RAMAN,
    "KP":     swe.SIDM_KRISHNAMURTI
}

# Лек калибриращ offset за айанамша (в градуси).
# 0.0 = чист Swiss Ephemeris (официално)
# напр. -0.01064 ≈ -38.3" → приближава DevaGuru/Jataka за твоя тест
NK_AYAN_OFFSET = float(os.getenv("NK_AYAN_OFFSET", "0.0"))

# базов сидерален режим (без offset-a; той се добавя ръчно)
swe.set_sid_mode(AYAN_MAP.get(AYAN, swe.SIDM_LAHIRI))

# === DevaGuru compatibility mode ===
NK_DEVA_MODE = os.getenv("NK_DEVA_MODE", "0") == "1"
NK_DEVA_UTC_OFFSET_SEC = float(os.getenv("NK_DEVA_UTC_OFFSET_SEC", "0"))

# ------------------ константи ------------------
SIGNS = [
    "Овен","Телец","Близнаци","Рак","Лъв","Дева",
    "Везни","Скорпион","Стрелец","Козирог","Водолей","Риби"
]
NAK = [
    "Ашвини","Бхарани","Криттика","Рохини","Мригашира","Ардра",
    "Пунаравасу","Пушя","Ашлеша","Магха","Пурва-Пхалгуни","Утара-Пхалгуни",
    "Хаста","Читра","Свати","Вишакха","Анурадха","Джиещха","Мула",
    "Пурва-Ашадха","Утара-Ашадха","Шравана","Дханишта","Шатабхиша",
    "Пурва-Бхадра","Утара-Бхадра","Ревати"
]

# ---------- PANCHANGA CONSTANTS ----------

TITHI_NAMES = [
    "1 растящ", "2 растящ", "3 растящ", "4 растящ", "5 растящ",
    "6 растящ", "7 растящ", "8 растящ", "9 растящ", "10 растящ",
    "11 растящ", "12 растящ", "13 растящ", "14 растящ", "15 Пурнима",
    "1 намаляващ", "2 намаляващ", "3 намаляващ", "4 намаляващ", "5 намаляващ",
    "6 намаляващ", "7 намаляващ", "8 намаляващ", "9 намаляващ", "10 намаляващ",
    "11 намаляващ", "12 намаляващ", "13 намаляващ", "14 намаляващ", "15 Амавасйа"
]

# Господари на тити – цикъл 8 планети (вкл. Раху)
TITHI_LORD_SEQ = [
    "Слънце","Луна","Марс","Меркурий","Юпитер","Венера","Сатурн","Раху"
]

# Вара (седмичен ден)
VARA_NAMES = [
    "Понеделник","Вторник","Сряда","Четвъртък",
    "Петък","Събота","Неделя"
]
VARA_LORDS = [
    "Луна",      # Понеделник
    "Марс",      # Вторник
    "Меркурий",  # Сряда
    "Юпитер",    # Четвъртък
    "Венера",    # Петък
    "Сатурн",    # Събота
    "Слънце"     # Неделя
]

# Господари на накшатри: 9-планетен цикъл
NAK_LORD_SEQ = [
    "Кету","Венера","Слънце","Луна","Марс","Раху","Юпитер","Сатурн","Меркурий"
]

# 27 йоги
YOGA_NAMES = [
    "Вишкумбха","Прити","Аюшман","Саубхагя","Шобхана","Атиганда",
    "Сукарма","Дхрити","Шула","Ганда","Вриддхи","Дхрува",
    "Вьягхата","Харшана","Ваджра","Сиддхи","Вьятипата","Варияна",
    "Паригха","Шива","Сиддха","Садхя","Шубха","Шукла",
    "Брахма","Индра","Вайдхрити"
]

# Лордове на йогите – подредени 1:1 с YOGA_NAMES
YOGA_LORDS = [
    "Юпитер",   # Вишкумбха (Vishkambha)
    "Слънце",   # Прити (Priti)
    "Венера",   # Аюшман (Ayushman)
    "Марс",     # Саубхагя (Saubhagya)
    "Луна",     # Шобхана (Shobhana)
    "Раху",     # Атиганда (Atiganda)
    "Юпитер",   # Сукарма (Sukarman)
    "Слънце",   # Дхрити (Dhriti)
    "Венера",   # Шула (Shula)
    "Марс",     # Ганда (Ganda)
    "Луна",     # Вриддхи (Vriddhi)
    "Раху",     # Дхрува (Dhruva)
    "Юпитер",   # Вьягхата (Vyaghata)
    "Слънце",   # Харшана (Harshana)  ← ТУК ИСКАМЕ СЛЪНЦЕ
    "Венера",   # Ваджра (Vajra)
    "Марс",     # Сиддхи (Siddhi)
    "Луна",     # Вьятипата (Vyatipata)
    "Раху",     # Варияна (Variyana)
    "Юпитер",   # Паригха (Parigha)
    "Слънце",   # Шива (Shiva)
    "Венера",   # Сиддха (Siddha)
    "Марс",     # Садхя (Sadhya)
    "Луна",     # Шубха (Shubha)
    "Раху",     # Шукла (Shukla)
    "Юпитер",   # Брахма (Brahma)
    "Слънце",   # Индра (Indra)
    "Венера",   # Вайдхрити (Vaidhriti)
]

# Карани
KARANA_MOVABLE = ["Бава","Балава","Каулaва","Тайтилa","Гара","Ваниджа","Вишти"]
KARANA_FIXED = ["Шакуни","Чатушпада","Нага","Кимстугна"]

KARANA_LORDS = {
    "Бава": "Луна",
    "Балава": "Луна",
    "Каулaва": "Марс",
    "Тайтилa": "Меркурий",
    "Гара": "Юпитер",
    "Ваниджа": "Венера",
    "Вишти": "Сатурн",
    "Шакуни": "Сатурн",
    "Чатушпада": "Марс",
    "Нага": "Раху",
    "Кимстугна": "Слънце",
}

# ---------- helper-и ----------

def sign_of(lon: float) -> str:
    return SIGNS[int((lon % 360)//30)]

def nak_pada(lon: float):
    span = 360.0 / 27.0
    idx = int((lon % 360.0) // span)
    pada = int(((lon % span) / (span / 4.0))) + 1
    return NAK[idx], pada

def current_karana_name(sun_lon: float, moon_lon: float) -> str:
    """
    Връща името на текущата Карана по класическата схема:

    1  -> Кимстугна (фиксирана)
    2–57  -> подвижните (Бава, Балава, Каулaва, Тайтилa, Гара, Ваниджа, Вишти) по цикъл
    58 -> Шакуни
    59 -> Чатушпада
    60 -> Нага
    """
    diff = (moon_lon - sun_lon) % 360.0
    k_num = int(diff / 6.0) + 1       # 1..60

    if k_num < 1:
        k_num = 1
    if k_num > 60:
        k_num = 60

    # 1-ва карана – Кимстугна
    if k_num == 1:
        return "Кимстугна"

    # последните 3 фиксирани
    if k_num >= 58:
        mapping = {
            58: "Шакуни",
            59: "Чатушпада",
            60: "Нага",
        }
        return mapping.get(k_num, "Нага")

    # подвижните: 2..57 (56 карани = 8 цикъла по 7)
    idx = (k_num - 2) % 7
    return KARANA_MOVABLE[idx]

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import swisseph as swe

def dt_to_jd(date_str: str, time_str: str, tz_str: str):
    tz = ZoneInfo(tz_str)
    fmt = "%Y-%m-%d %H:%M:%S" if len(time_str.split(":")) == 3 else "%Y-%m-%d %H:%M"
    dt_local = datetime.strptime(f"{date_str} {time_str}", fmt).replace(tzinfo=tz)
    dt_utc = dt_local.astimezone(timezone.utc)

    # (по желание) микро-офсет за DevaGuru (ако решиш)
    if NK_DEVA_MODE and NK_DEVA_UTC_OFFSET_SEC != 0:
        dt_utc = dt_utc + timedelta(seconds=NK_DEVA_UTC_OFFSET_SEC)

    ut_hour = dt_utc.hour + dt_utc.minute/60.0 + dt_utc.second/3600.0
    jd_ut = swe.julday(dt_utc.year, dt_utc.month, dt_utc.day, ut_hour)  # UT

    return jd_ut, dt_utc

# ---- Флагове ----
FLAGS_TROP = swe.FLG_SWIEPH | swe.FLG_SPEED
FLAGS_SID  = swe.FLG_SWIEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED

def _ayanamsha_deg_ut(jd_ut: float) -> float:
    # sid mode се сетва ОТВЪН, тук само четем
    return swe.get_ayanamsa_ut(jd_ut) + NK_AYAN_OFFSET

def _sidereal_from_tropical(trop_lon: float, ayan: float) -> float:
    return (trop_lon - ayan) % 360.0

def planet_longitudes(jd: float, use_sidereal: bool = True):
    ayan = _ayanamsha_deg_ut(jd) if use_sidereal else 0.0

    plist = [
        (swe.SUN,     "Слънце"),
        (swe.MOON,    "Луна"),
        (swe.MERCURY, "Меркурий"),
        (swe.VENUS,   "Венера"),
        (swe.MARS,    "Марс"),
        (swe.JUPITER, "Юпитер"),
        (swe.SATURN,  "Сатурн"),
    ]

    out = []
    for pid, name in plist:
        pos, _ = swe.calc_ut(jd, pid, FLAGS_TROP)
        trop = pos[0] % 360.0
        spd  = pos[3]
        retro = spd < 0

        lon = ((trop - ayan) % 360.0) if use_sidereal else trop
        n, p = nak_pada(lon)

        out.append({
            "planet": name,
            "longitude": round(lon, 6),
            "sign": sign_of(lon),
            "nakshatra": n,
            "pada": p,
            "retrograde": retro
        })

    # Раху/Кету
    node_id = swe.TRUE_NODE if NODE == "TRUE" else swe.MEAN_NODE
    npos, _ = swe.calc_ut(jd, node_id, FLAGS_TROP)
    trop_rahu = npos[0] % 360.0

    rahu = ((trop_rahu - ayan) % 360.0) if use_sidereal else trop_rahu
    ketu = (rahu + 180.0) % 360.0

    r_n, r_p = nak_pada(rahu)
    k_n, k_p = nak_pada(ketu)

    out.append({
        "planet": "Раху",
        "longitude": round(rahu, 6),
        "sign": sign_of(rahu),
        "nakshatra": r_n,
        "pada": r_p,
        "retrograde": False
    })
    out.append({
        "planet": "Кету",
        "longitude": round(ketu, 6),
        "sign": sign_of(ketu),
        "nakshatra": k_n,
        "pada": k_p,
        "retrograde": False
    })

    return out

    
def compute_arudha_lagna(asc_sign_index, planets):
    """
    Арудха Лагна (според традицията на Шри Ачютананда / Академия Джатака)
    """
    # Владетели на знаците
    rulers = ["Марс","Венера","Меркурий","Луна","Слънце","Меркурий",
              "Венера","Марс","Юпитер","Сатурн","Сатурн","Юпитер"]

    asc_lord = rulers[asc_sign_index]
    lord = next((p for p in planets if p["planet"] == asc_lord), None)
    if not lord:
        return None

    lord_sign_index = SIGNS.index(lord["sign"])

    # Разстояние от Лагна до знака на лорда (1-based, но ние работим с 0-based)
    diff = (lord_sign_index - asc_sign_index) % 12

    # ---- Специални правила на Академия Джатака ----
    if diff in (3, 9):  # 4-ти или 10-ти от лагна
        al_index = (asc_sign_index + 3) % 12
    elif diff in (0, 6):  # 1-ви или 7-ми от лагна
        al_index = (asc_sign_index + 9) % 12  # 10-ти дом
    else:
        al_index = (lord_sign_index + diff) % 12
        # ако AL попада в 1-ви или 7-ми от лагна, премести с +10
        rel = (al_index - asc_sign_index) % 12
        if rel in (0, 6):
            al_index = (al_index + 10) % 12

    return SIGNS[al_index]

def compute_chara_karakas(planets):
    """
    8 Chara Karaka (традиция Шри Ачютананда):
    кандидати = 7 грахи + Раху (Кету не участва).
    Раху: rel = 30° - (lon % 30°).
    """
    if not planets:
        return {}

    cand = []
    for p in planets:
        name = p.get("planet")
        if name == "Кету":
            continue
        try:
            lon = float(p.get("longitude", 0.0)) % 360.0
        except Exception:
            lon = 0.0

        rel = lon % 30.0
        if name == "Раху":
            rel = 30.0 - rel

        cand.append((name, rel))

    if not cand:
        return {}

    cand.sort(key=lambda x: x[1], reverse=True)

    labels = [
        ("АК",  "Атмакаракa"),
        ("АмК", "Аматякаракa"),
        ("БК",  "Бхратрукаракa"),
        ("МК",  "Матрукаракa"),
        ("ПиК", "Питрукаракa"),
        ("ПК",  "Путракаракa"),
        ("ГК",  "Гнатикаракa"),
        ("ДК",  "Даракаракa"),
    ]

    karakas = {}
    for (name, _rel), (code, _full) in zip(cand, labels):
        karakas[name] = code

    return karakas

def compute_panchanga(jd: float, dt_local, sun_lon: float, moon_lon: float):
    """
    Панчанга:
    Титхи, Вара, Накшатра, Йога, Карана – име + управител + % остатък (където има смисъл).
    """

    # ---------- TITHI ----------
    diff = (moon_lon - sun_lon) % 360.0
    tithi_size = 12.0  # градуса на една титхи
    tithi_index = int(diff / tithi_size)  # 0..29
    tithi_index = max(0, min(29, tithi_index))
    tithi_name = TITHI_NAMES[tithi_index]
    tithi_lord = TITHI_LORD_SEQ[tithi_index % len(TITHI_LORD_SEQ)]

    # колко е минало / остава в текущата титхи
    tithi_offset = diff - tithi_index * tithi_size   # 0..12
    tithi_frac    = tithi_offset / tithi_size        # 0..1 (изминало)
    tithi_left    = max(0.0, 1.0 - tithi_frac)       # 0..1 (остава)
    tithi_left_pct = tithi_left * 100.0

    # ---------- VARA ----------
    wd = dt_local.weekday()  # 0=Mon..6=Sun
    vara_name = VARA_NAMES[wd]
    vara_lord = VARA_LORDS[wd]
    # тук НЕ даваме процент (няма смисъл) → няма left_percent

    # ---------- NAKSHATRA ----------
    nak_name, _ = nak_pada(moon_lon)
    try:
        nak_idx = NAK.index(nak_name)
    except ValueError:
        nak_idx = 0
    nak_lord = NAK_LORD_SEQ[nak_idx % len(NAK_LORD_SEQ)]

    nak_span   = 360.0 / 27.0
    nak_offset = (moon_lon % 360.0) - nak_idx * nak_span     # 0..nak_span
    nak_frac   = nak_offset / nak_span                       # изминало
    nak_left   = max(0.0, 1.0 - nak_frac)
    nak_left_pct = nak_left * 100.0

    # ---------- YOGA ----------
    span = 360.0 / 27.0
    yoga_val = (sun_lon + moon_lon) % 360.0
    yoga_index = int(yoga_val / span)
    yoga_index = max(0, min(26, yoga_index))
    yoga_name = YOGA_NAMES[yoga_index]
    yoga_lord = YOGA_LORDS[yoga_index]   # ползваш списъка, който оправихме

    yoga_offset = yoga_val - yoga_index * span
    yoga_frac   = yoga_offset / span
    yoga_left   = max(0.0, 1.0 - yoga_frac)
    yoga_left_pct = yoga_left * 100.0

    # ---------- KARANA ----------
    karana_name = current_karana_name(sun_lon, moon_lon)
    karana_lord = KARANA_LORDS.get(karana_name, "")

    kar_span = 6.0  # 360/60
    k_num = int(diff / kar_span) + 1     # 1..60
    k_num = max(1, min(60, k_num))

    kar_offset = diff - (k_num - 1) * kar_span  # 0..6
    kar_frac   = kar_offset / kar_span
    kar_left   = max(0.0, 1.0 - kar_frac)
    kar_left_pct = kar_left * 100.0

    return {
        "tithi": {
            "name": tithi_name,
            "lord": tithi_lord,
            "left_percent": tithi_left_pct,
        },
        "vara": {
            "name": vara_name,
            "lord": vara_lord,
            # без left_percent – както искаш
        },
        "nakshatra": {
            "name": nak_name,
            "lord": nak_lord,
            "left_percent": nak_left_pct,
        },
        "yoga": {
            "name": yoga_name,
            "lord": yoga_lord,
            "left_percent": yoga_left_pct,
        },
        "karana": {
            "name": karana_name,
            "lord": karana_lord,
            "left_percent": kar_left_pct,
        }
    }

# ---------- VIMSHOTTARI DASHA ----------

# редът на лордовете (съвпада с господарите на накшатри)
DASHA_SEQ = ["Кету","Венера","Слънце","Луна","Марс","Раху","Юпитер","Сатурн","Меркурий"]
# дължини (години) на махадашите
DASHA_YEARS = {
    "Кету": 7, "Венера": 20, "Слънце": 6, "Луна": 10, "Марс": 7,
    "Раху": 18, "Юпитер": 16, "Сатурн": 19, "Меркурий": 17
}
SID_NAK_SPAN = 360.0 / 27.0

def nak_index_from_lon(lon: float) -> int:
    """0..26 индекс на накшатра по сидерален лонгитуд."""
    return int(((lon % 360.0) + 360.0) % 360.0 // SID_NAK_SPAN)

def years_to_days(y: float) -> float:
    return y * 365.25
    # тропическа година - астрономично точна
    # return y * 365.2425

def add_days(dt, days: float):
    from datetime import timedelta
    return dt + timedelta(days=days)

def dasha_order_from(start_lord: str):
    """Връща последователността на лордовете, започвайки от start_lord."""
    i = DASHA_SEQ.index(start_lord)
    return DASHA_SEQ[i:] + DASHA_SEQ[:i]

def vimsottari_generate(birth_dt_utc: datetime, moon_lon_sid: float, horizon_years: float = 120.0):
    """
    Генерира Вимшоттари до 'horizon_years' от раждането.
    Връща списък от махадаши с антар-даши вътре (2-ро ниво).
    """
    # начален лорд според лунната накшатра
    nk_idx = nak_index_from_lon(moon_lon_sid)
    start_lord = DASHA_SEQ[nk_idx % 9]

    # степен в текущата накшатра → остатък от първата махадаша
    start_of_nk = nk_idx * SID_NAK_SPAN
    passed_in_nk = ((moon_lon_sid % 360.0) - start_of_nk) % SID_NAK_SPAN
    frac = passed_in_nk / SID_NAK_SPAN            # 0..1 преминал дял
    remain_frac = 1.0 - frac

    order = dasha_order_from(start_lord)

    out = []
    t0 = birth_dt_utc
    age0 = 0.0

    # първа махадаша – остатък
    first_y = DASHA_YEARS[start_lord] * remain_frac
    t1 = add_days(t0, years_to_days(first_y))
    out.append({
        "lord": start_lord,
        "start": t0.isoformat(timespec="seconds"),
        "end":   t1.isoformat(timespec="seconds"),
        # предишно
        # "start": t0.date().isoformat(),
        # "end":   t1.date().isoformat(),
        "age_start": age0,
        "age_end":   age0 + first_y,
        "antar": []  # попълваме по-долу
    })
    # следващи махадаши
    cur_t = t1
    cur_age = age0 + first_y
    # въртим цикъл докато стигнем хоризонта
    k = 1
    while cur_age < horizon_years + 1e-6:
        lord = order[k % 9]
        dur_y = float(DASHA_YEARS[lord])
        start = cur_t
        end   = add_days(start, years_to_days(dur_y))
        out.append({
            "lord": lord,
            "start": start.date().isoformat(),
            "end":   end.date().isoformat(),
            "age_start": cur_age,
            "age_end":   cur_age + dur_y,
            "antar": []
        })
        cur_t = end
        cur_age += dur_y
        k += 1

    # антар-даши за всяка махадаша
    for row in out:
        m_lord = row["lord"]
        m_years = DASHA_YEARS[m_lord]
        # редът на под-лордове започва от лорда на махадашата
        sub_order = dasha_order_from(m_lord)
        sub_start = datetime.fromisoformat(row["start"])
        sub_d = 0.0
        antar_rows = []
        for s_lord in sub_order:
            share = DASHA_YEARS[s_lord] / 120.0      # дял от 120-годишния цикъл
            sub_y = m_years * share                  # години на антрадaша
            s0 = add_days(sub_start, years_to_days(sub_d))
            s1 = add_days(sub_start, years_to_days(sub_d + sub_y))
            antar_rows.append({
                "lord": s_lord,
                "start": s0.date().isoformat(),
                "end":   s1.date().isoformat(),
                "years": sub_y
            })
            sub_d += sub_y
        row["antar"] = antar_rows

    return out

def houses_safe(jd, lat, lon, flags=None, hsys=b'P'):
    """
    Унифициран достъп до houses_ex / houses за различни версии на pyswisseph.
    """
    try:
        if flags is not None:
            return swe.houses_ex(jd, flags, lat, lon, hsys)
        else:
            return swe.houses_ex(jd, lat, lon, hsys)
    except TypeError:
        try:
            return swe.houses_ex(jd, lat, lon, hsys)
        except Exception:
            cusps, ascmc = swe.houses(jd, lat, lon, hsys)
            return (cusps, ascmc)
def deg_in_sign(lon: float) -> float:
    return lon % 30.0

def navamsa_sign_index(sign_idx: int, deg_in: float) -> int:
    """
    D9 (Навамша) – правило на Парашара:
    - Подвижни (Овен, Рак, Везни, Козирог): старт от същия знак
    - Неподвижни (Телец, Лъв, Скорпион, Водолей): старт от 9-тия от себе си (+8)
    - Двойствени (Близнаци, Дева, Стрелец, Риби): старт от 5-тия от себе си (+4)
    После броим пада (0..8) и въртим от стартовия знак.
    """
    pada = int(deg_in / (30.0 / 9.0))  # 0..8

    if sign_idx in (0, 3, 6, 9):         # подвижни
        start = sign_idx
    elif sign_idx in (1, 4, 7, 10):      # неподвижни
        start = (sign_idx + 8) % 12
    else:                                # двойствени
        start = (sign_idx + 4) % 12

    return (start + pada) % 12

def d9_sign_name_from_lon(lon: float) -> str:
    """Връща името на знака (от SIGNS) за даден сидерален лонгитуд в D9."""
    sidx = int((lon % 360.0) // 30)
    d_in = deg_in_sign(lon)
    d9_idx = navamsa_sign_index(sidx, d_in)
    return SIGNS[d9_idx]

@app.after_request
def add_cors(resp):
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    resp.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    return resp

# ---------- HEALTH ----------
@app.route('/health', methods=['GET'])
def health():
    return jsonify(ok=True), 200

# ---------- DEBUG ----------
@app.route('/debug', methods=['GET'], endpoint='nk_debug')
def debug():
    try:
        date_str = "1988-05-24"
        time_str = "12:00"
        tz_str   = "Europe/Sofia"
        lat      = 43.2141
        lon      = 27.9147

        dt_local = datetime.strptime(
            f"{date_str} {time_str}", "%Y-%m-%d %H:%M"
        ).replace(tzinfo=ZoneInfo(tz_str))
        dt_utc   = dt_local.astimezone(timezone.utc)
        ut_hour  = dt_utc.hour + dt_utc.minute/60.0 + dt_utc.second/3600.0
        jd       = swe.julday(dt_utc.year, dt_utc.month, dt_utc.day, ut_hour)

        def compute_variant(label, ayanamsha_const, node_is_true):
            swe.set_sid_mode(ayanamsha_const)
            houses, ascmc = houses_safe(jd, lat, lon, flags=FLAGS_TROP, hsys=b'P')
            asc_trop = ascmc[0] % 360.0
            ay = _ayanamsha_deg_ut(jd)
            asc = _sidereal_from_tropical(asc_trop, ay)

            res = {
                "label": label,
                "Ascendant": {
                    "degree": round(asc, 4),
                    "sign": sign_of(asc)
                },
                "Planets": []
            }

            for pid, name in [
                (swe.SUN, "Слънце"), (swe.MOON,"Луна"), (swe.MERCURY,"Меркурий"),
                (swe.VENUS,"Венера"), (swe.MARS,"Марс"),
                (swe.JUPITER,"Юпитер"), (swe.SATURN,"Сатурн")
            ]:
                pos, _ = swe.calc_ut(jd, pid, FLAGS_TROP)
                trop = pos[0] % 360.0
                ay = _ayanamsha_deg_ut(jd)
                L = _sidereal_from_tropical(trop, ay)
                n, p = nak_pada(L)
                res["Planets"].append({
                    "planet": name,
                    "longitude": round(L, 4),
                    "sign": sign_of(L),
                    "nakshatra": n,
                    "pada": p
                })

            node_id = swe.TRUE_NODE if node_is_true else swe.MEAN_NODE
            node_pos, _ = swe.calc_ut(jd, node_id, FLAGS_TROP)
            trop_rah = node_pos[0] % 360.0
            ay = _ayanamsha_deg_ut(jd)
            rahu_L = _sidereal_from_tropical(trop_rah, ay)
            ketu_L = (rahu_L + 180.0) % 360.0
            r_n, r_p = nak_pada(rahu_L)
            k_n, k_p = nak_pada(ketu_L)

            res["Planets"].append({
                "planet": "Раху",
                "longitude": round(rahu_L, 4),
                "sign": sign_of(rahu_L),
                "nakshatra": r_n,
                "pada": r_p
            })
            res["Planets"].append({
                "planet": "Кету",
                "longitude": round(ketu_L, 4),
                "sign": sign_of(ketu_L),
                "nakshatra": k_n,
                "pada": k_p
            })

            return res

        variants = [
            compute_variant("LAHIRI_MEAN+OFF", swe.SIDM_LAHIRI, False),
        ]

        swe.set_sid_mode(AYAN_MAP.get(AYAN, swe.SIDM_LAHIRI))

        return jsonify({
            "ok": True,
            "ayan_offset": NK_AYAN_OFFSET,
            "sidereal_variants": variants
        }), 200

    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500

# ---------- CALCULATE ----------
@app.route('/calculate', methods=['POST', 'OPTIONS'])
def calculate():
    if request.method == 'OPTIONS':
        return ('', 204)
    try:
        data = request.get_json(force=True)
        date_str = data.get('date')
        time_str = data.get('time')
        tz_str   = data.get('timezone')
        lat = float(data.get('lat'))
        lon = float(data.get('lon'))

        jd, dt_utc = dt_to_jd(date_str, time_str, tz_str)
        dt_local = dt_utc.astimezone(ZoneInfo(tz_str))

        # Ascendant — директно сидерален (DevaGuru style)
        swe.set_sid_mode(AYAN_MAP.get(AYAN, swe.SIDM_LAHIRI))
        swe.set_topo(lon, lat, 0)
        houses, ascmc = houses_safe(
            jd,
            lat,
            lon,
            flags=swe.FLG_SIDEREAL | swe.FLG_TOPOCTR,
            hsys=b'P'
        )
        asc = ascmc[0] % 360.0

        # Asc: тропически → сидерален с нашата айанамша+offset
        # ayan = _ayanamsha_deg_ut(jd)
        # houses, ascmc = houses_safe(jd, lat, lon, flags=FLAGS_TROP, hsys=b'P')
        # asc_trop = ascmc[0] % 360.0
        # asc = _sidereal_from_tropical(asc_trop, ayan)

        # Планети (сидерално)
        planets = planet_longitudes(jd, use_sidereal=True)

        # Слънце/Луна за Панчанга (ползваме вече сидералните)
        sun_lon = next((p["longitude"] for p in planets if p["planet"] == "Слънце"), None)
        moon_lon = next((p["longitude"] for p in planets if p["planet"] == "Луна"), None)

        panchanga = None
        if sun_lon is not None and moon_lon is not None:
            panchanga = compute_panchanga(jd, dt_local, sun_lon, moon_lon)

        # 8 Chara Karaka с Раху (без Кету)
        ck_map = compute_chara_karakas(planets)
        for p in planets:
            name = p.get("planet")
            if name in ck_map:
                p["chara_karaka"] = ck_map[name]
                
        # --- D9 Навамша ---
        d9_planets = []
        for p in planets:
            d9_sign = d9_sign_name_from_lon(p["longitude"])
            d9_planets.append({
                "planet": p["planet"],
                "sign": d9_sign,
                "retrograde": bool(p.get("retrograde"))
            })
        d9_asc_sign = d9_sign_name_from_lon(asc)

        # AL за D9 (по същото правило като при D1)
        try:
            asc_idx_d9 = SIGNS.index(d9_asc_sign)
            al_d9_sign = compute_arudha_lagna(asc_idx_d9, d9_planets)
        except Exception:
            al_d9_sign = None

        # Базов отговор
        res = {
            "config": {
                "ayanamsha": AYAN,
                "node_type": NODE,
                "ephe_path": EPHE_PATH,
                "ayan_offset": NK_AYAN_OFFSET
            },
            "Ascendant": {
                "degree": round(asc, 6),
                "sign": sign_of(asc)
            },
            "Planets": planets,
            "D9": {
                "Ascendant": {"sign": d9_asc_sign},
                "ArudhaLagna": ({"sign": al_d9_sign} if al_d9_sign else None),
                "Planets": d9_planets
            }
        }

        # Арудха Лагна (Arudha Lagna), съвместима с фронта
        try:
            asc_index = SIGNS.index(sign_of(asc))
            al_sign = compute_arudha_lagna(asc_index, planets)
            if al_sign:
                # фронтът очаква или {degree}, или {sign}
                res["ArudhaLagna"] = {"sign": al_sign}
        except Exception:
            # не чупим нищо, ако нещо се обърка
            pass

        # Панчанга
        if panchanga:
            res["Panchanga"] = panchanga
        # --- Вимшоттари-даша (на база сидералната Луна) ---
        try:
            if moon_lon is not None:
                vim = vimsottari_generate(dt_utc, float(moon_lon), horizon_years=120.0)
                if vim:
                    res["Vimshottari"] = vim
        except Exception:
            pass

        return jsonify(res), 200

    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e),
            "trace": traceback.format_exc()
        }), 500

# ---------- ROOT ----------
@app.route('/')
def home():
    return f"Astro Calculator API is running (AYAN={AYAN}, NODE={NODE}, AYAN_OFFSET={NK_AYAN_OFFSET})"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
