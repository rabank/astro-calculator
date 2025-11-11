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
NK_AYAN_OFFSET = float(os.getenv("NK_AYAN_OFFSET", "-0.0105913"))

# базов сидерален режим (без offset-a; той се добавя ръчно)
swe.set_sid_mode(AYAN_MAP.get(AYAN, swe.SIDM_LAHIRI))

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

# за старт – същият цикъл като NAK_LORD_SEQ
YOGA_LORD_SEQ = NAK_LORD_SEQ

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
    diff = (moon_lon - sun_lon) % 360.0
    k_num = int(diff / 6.0) + 1  # 1..60

    if k_num < 1:
        k_num = 1
    if k_num > 60:
        k_num = 60

    if k_num >= 57:
        mapping = {
            57: "Шакуни",
            58: "Чатушпада",
            59: "Нага",
            60: "Кимстугна"
        }
        return mapping.get(k_num, "Кимстугна")

    idx = (k_num - 1) % 7
    return KARANA_MOVABLE[idx]

def dt_to_jd(date_str: str, time_str: str, tz_str: str):
    dt_local = datetime.strptime(
        f"{date_str} {time_str}", "%Y-%m-%d %H:%M"
    ).replace(tzinfo=ZoneInfo(tz_str))
    dt_utc   = dt_local.astimezone(timezone.utc)
    ut_hour  = dt_utc.hour + dt_utc.minute/60.0 + dt_utc.second/3600.0
    jd       = swe.julday(dt_utc.year, dt_utc.month, dt_utc.day, ut_hour)   # UT
    return jd, dt_utc

# ---- Флагове ----
FLAGS_TROP = swe.FLG_SWIEPH | swe.FLG_SPEED
FLAGS_SID  = swe.FLG_SWIEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED

def _ayanamsha_deg_ut(jd: float) -> float:
    swe.set_sid_mode(swe.SIDM_LAHIRI)
    base = swe.get_ayanamsa_ut(jd)
    return base + NK_AYAN_OFFSET

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

        lon  = _sidereal_from_tropical(trop, ayan) if use_sidereal else trop
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
    rahu = _sidereal_from_tropical(trop_rahu, ayan) if use_sidereal else trop_rahu
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
    # владетели на знаците (в реда на SIGNS)
    rulers = ["Марс","Венера","Меркурий","Луна","Слънце","Меркурий",
              "Венера","Марс","Юпитер","Сатурн","Сатурн","Юпитер"]

    asc_lord = rulers[asc_sign_index]
    lord = next((p for p in planets if p["planet"] == asc_lord), None)
    if not lord:
        return None

    lord_sign_index = SIGNS.index(lord["sign"])
    diff = (lord_sign_index - asc_sign_index) % 12
    al_index = (lord_sign_index + diff) % 12

    # ако AL съвпада с лагна или със знака на лорда → добавяме +10
    if al_index == asc_sign_index or al_index == lord_sign_index:
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
    Минимална Панчанга:
    Титхи, Вара, Накшатра, Йога, Карана – име + управител.
    """
    # Tithi
    diff = (moon_lon - sun_lon) % 360.0
    tithi_index = int(diff / 12.0)  # 0..29
    tithi_index = max(0, min(29, tithi_index))
    tithi_name = TITHI_NAMES[tithi_index]
    tithi_lord = TITHI_LORD_SEQ[tithi_index % len(TITHI_LORD_SEQ)]

    # Vara
    wd = dt_local.weekday()  # 0=Mon..6=Sun
    vara_name = VARA_NAMES[wd]
    vara_lord = VARA_LORDS[wd]

    # Nakshatra
    nak_name, _ = nak_pada(moon_lon)
    try:
        nak_idx = NAK.index(nak_name)
    except ValueError:
        nak_idx = 0
    nak_lord = NAK_LORD_SEQ[nak_idx % len(NAK_LORD_SEQ)]

    # Yoga
    span = 360.0 / 27.0
    yoga_val = (sun_lon + moon_lon) % 360.0
    yoga_index = int(yoga_val / span)
    yoga_index = max(0, min(26, yoga_index))
    yoga_name = YOGA_NAMES[yoga_index]
    yoga_lord = YOGA_LORD_SEQ[yoga_index % len(YOGA_LORD_SEQ)]

    # Karana
    karana_name = current_karana_name(sun_lon, moon_lon)
    karana_lord = KARANA_LORDS.get(karana_name, "")

    return {
        "tithi": {
            "name": tithi_name,
            "lord": tithi_lord,
        },
        "vara": {
            "name": vara_name,
            "lord": vara_lord,
        },
        "nakshatra": {
            "name": nak_name,
            "lord": nak_lord,
        },
        "yoga": {
            "name": yoga_name,
            "lord": yoga_lord,
        },
        "karana": {
            "name": karana_name,
            "lord": karana_lord,
        }
    }

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

        # инфо
        swe.set_sid_mode(AYAN_MAP.get(AYAN, swe.SIDM_LAHIRI))

        # Asc: тропически → сидерален с нашата айанамша+offset
        ayan = _ayanamsha_deg_ut(jd)
        houses, ascmc = houses_safe(jd, lat, lon, flags=FLAGS_TROP, hsys=b'P')
        asc_trop = ascmc[0] % 360.0
        asc = _sidereal_from_tropical(asc_trop, ayan)

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
            "Planets": planets
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
