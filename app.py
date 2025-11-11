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

def sign_of(lon: float) -> str:
    return SIGNS[int((lon % 360)//30)]

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
# Планети: винаги тропикално, после вадим (Lahiri + offset) ръчно
FLAGS_TROP = swe.FLG_SWIEPH | swe.FLG_SPEED
# Къщи: по-долу вече ще взимаме тропически Asc и ще го обръщаме сами
FLAGS_SID  = swe.FLG_SWIEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED

def _ayanamsha_deg_ut(jd: float) -> float:
    """
    Връща (Lahiri айанамша + NK_AYAN_OFFSET).
    Offset-ът е нашата фина калибровка към Deva/Jataka, ако решиш да го ползваш.
    """
    swe.set_sid_mode(swe.SIDM_LAHIRI)
    base = swe.get_ayanamsa_ut(jd)
    return base + NK_AYAN_OFFSET

def _sidereal_from_tropical(trop_lon: float, ayan: float) -> float:
    return (trop_lon - ayan) % 360.0

def planet_longitudes(jd: float, use_sidereal: bool = True):
    """
    1) calc_ut с FLAGS_TROP → тропикални дължини
    2) ако use_sidereal=True → lon = trop - (Lahiri + NK_AYAN_OFFSET)
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
        pos, _ = swe.calc_ut(jd, pid, FLAGS_TROP)
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

    # Раху/Кету (mean/true) със същата логика
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
            # тропически Asc → сидерален със същата формула както за планетите
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

        # глобален сидерален режим (само за инфо/съвместимост)
        swe.set_sid_mode(AYAN_MAP.get(AYAN, swe.SIDM_LAHIRI))

        # Asc: тропически от houses_ex + същата айанамша+offset както за планетите
        ayan = _ayanamsha_deg_ut(jd)
        houses, ascmc = houses_safe(jd, lat, lon, flags=FLAGS_TROP, hsys=b'P')
        asc_trop = ascmc[0] % 360.0
        asc = _sidereal_from_tropical(asc_trop, ayan)

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
    return f"Astro Calculator API is running (AYAN={AYAN}, NODE={NODE}, AYAN_OFFSET={NK_AYAN_OFFSET})"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
