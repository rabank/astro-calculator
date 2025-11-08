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
# Ако не са сетнати, ползваме LAHIRI + MEAN node
AYAN = os.getenv("AYANAMSHA", "LAHIRI").upper()   # LAHIRI | RAMAN | KP
NODE = os.getenv("NODE_TYPE", "MEAN").upper()     # TRUE | MEAN

AYAN_MAP = {
    "LAHIRI": swe.SIDM_LAHIRI,          # Chitrapaksha
    "RAMAN":  swe.SIDM_RAMAN,
    "KP":     swe.SIDM_KRISHNAMURTI,
}

# Фино изместване на айанамшата (в градуси).
# По подразбиране 0.0 — чист Lahiri.
# Настройва се през env NK_AYAN_OFFSET, ако искаш да се застопориш към Deva/Jataka.
NK_AYAN_OFFSET = float(os.getenv("NK_AYAN_OFFSET", "0.0"))

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

def sign_of(lon: float) -> str:
    return SIGNS[int((lon % 360.0)//30)]

def nak_pada(lon: float):
    span = 360.0 / 27.0
    idx = int((lon % 360.0) // span)
    pada = int(((lon % span) / (span / 4.0))) + 1
    return NAK[idx], pada

def dt_to_jd(date_str: str, time_str: str, tz_str: str):
    dt_local = datetime.strptime(
        f"{date_str} {time_str}", "%Y-%m-%d %H:%M"
    ).replace(tzinfo=ZoneInfo(tz_str))
    dt_utc   = dt_local.astimezone(timezone.utc)
    ut_hour  = dt_utc.hour + dt_utc.minute/60.0 + dt_utc.second/3600.0
    jd       = swe.julday(dt_utc.year, dt_utc.month, dt_utc.day, ut_hour)   # UT
    return jd, dt_utc

# ---- Флагове ----
# Планети: тропикални, после правим сидерално чрез айанамша
FLAGS_TROP_PLANETS = swe.FLG_SWIEPH | swe.FLG_SPEED
# Къщи (Asc): тропикален Placidus; после същата айанамша
FLAGS_TROP_HOUSES  = swe.FLG_SWIEPH

def _ayanamsha_deg_ut(jd: float) -> float:
    """
    LAHIRI (или избрания режим) + NK_AYAN_OFFSET.
    Ползваме я РЪЧНО за всички тела и Asc.
    """
    swe.set_sid_mode(AYAN_MAP.get(AYAN, swe.SIDM_LAHIRI))
    base = swe.get_ayanamsa_ut(jd)
    return base + NK_AYAN_OFFSET

def _sidereal_from_tropical(trop_lon: float, ayan: float) -> float:
    return (trop_lon - ayan) % 360.0

def planet_longitudes(jd: float, use_sidereal: bool = True):
    """
    1) calc_ut с FLAGS_TROP_PLANETS (тропикално)
    2) ако use_sidereal=True → lon = trop - (ayan + offset)
    Всички тела ползват ЕДНА и съща айанамша.
    """
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
        pos, _ = swe.calc_ut(jd, pid, FLAGS_TROP_PLANETS)
        trop = pos[0] % 360.0
        lon  = _sidereal_from_tropical(trop, ayan) if use_sidereal else trop
        n, p = nak_pada(lon)
        out.append({
            "planet": name,
            "longitude": round(lon, 6),
            "sign": sign_of(lon),
            "nakshatra": n,
            "pada": p
        })

    # Възли (true/mean според NODE), по същата схема
    node_id = swe.TRUE_NODE if NODE == "TRUE" else swe.MEAN_NODE
    npos, _ = swe.calc_ut(jd, node_id, FLAGS_TROP_PLANETS)
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
        "pada": r_p
    })
    out.append({
        "planet": "Кету",
        "longitude": round(ketu, 6),
        "sign": sign_of(ketu),
        "nakshatra": k_n,
        "pada": k_p
    })

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
        # Тестов пример
        date_str = "1988-05-24"
        time_str = "12:00"
        tz_str   = "Europe/Sofia"
        lat      = 43.2141
        lon      = 27.9147

        jd, _ = dt_to_jd(date_str, time_str, tz_str)
        ayan = _ayanamsha_deg_ut(jd)

        # Asc tropical -> sidereal
        houses_t, ascmc_t = houses_safe(jd, lat, lon, flags=FLAGS_TROP_HOUSES, hsys=b'P')
        asc_trop = ascmc_t[0] % 360.0
        asc_sid  = _sidereal_from_tropical(asc_trop, ayan)

        return jsonify({
            "ok": True,
            "input": {
                "date": date_str,
                "time": time_str,
                "tz": tz_str,
                "lat": lat,
                "lon": lon
            },
            "ayanamsha": {
                "mode": AYAN,
                "offset_deg": NK_AYAN_OFFSET,
                "value_deg": ayan
            },
            "Ascendant": {
                "tropical_deg": asc_trop,
                "sidereal_deg": asc_sid,
                "sign": sign_of(asc_sid)
            },
            "Planets": planet_longitudes(jd, use_sidereal=True)
        }), 200

    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500

# ---------- CALCULATE ----------
@app.route('/calculate', methods=['POST','OPTIONS'])
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

        jd, _ = dt_to_jd(date_str, time_str, tz_str)
        ayan = _ayanamsha_deg_ut(jd)

        # Asc: тропикален Placidus, после същата айанамша
        houses_t, ascmc_t = houses_safe(jd, lat, lon, flags=FLAGS_TROP_HOUSES, hsys=b'P')
        asc_trop = ascmc_t[0] % 360.0
        asc_sid  = _sidereal_from_tropical(asc_trop, ayan)

        res = {
            "config": {
                "ayanamsha": AYAN,
                "ayan_offset": NK_AYAN_OFFSET,
                "node_type": NODE,
                "ephe_path": EPHE_PATH,
            },
            "Ascendant": {
                "degree": round(asc_sid, 6),
                "sign": sign_of(asc_sid)
            },
            "Planets": planet_longitudes(jd, use_sidereal=True)
        }
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
    return f"Astro Calculator API is running (AYAN={AYAN}, NODE={NODE}, NK_AYAN_OFFSET={NK_AYAN_OFFSET})"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
