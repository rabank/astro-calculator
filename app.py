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
# Можеш да ги оставиш така; ако не са сетнати, ползваме LAHIRI + MEAN node
AYAN = os.getenv("AYANAMSHA", "LAHIRI").upper()   # LAHIRI | RAMAN | KP
NODE = os.getenv("NODE_TYPE", "MEAN").upper()     # TRUE | MEAN

AYAN_MAP = {
    "LAHIRI": swe.SIDM_LAHIRI,          # Chitrapaksha
    "RAMAN":  swe.SIDM_RAMAN,
    "KP":     swe.SIDM_KRISHNAMURTI
}

# по подразбиране – LAHIRI, ако е нещо друго
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
# Планети: винаги тропикално, после вадим айанамша ръчно
FLAGS_TROP = swe.FLG_SWIEPH | swe.FLG_SPEED | swe.FLG_TRUEPOS
# Къщи: сидерални (Lahiri) за Asc
FLAGS_SID  = swe.FLG_SWIEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED

def _ayanamsha_deg_ut(jd: float) -> float:
    # фиксираме LAHIRI за консистентност с JHora/Deva
    swe.set_sid_mode(swe.SIDM_LAHIRI)
    return swe.get_ayanamsa_ut(jd)

def _sidereal_from_tropical(trop_lon: float, ayan: float) -> float:
    return (trop_lon - ayan) % 360.0

def planet_longitudes(jd: float, use_sidereal: bool = True):
    """
    Винаги смятаме тропикални дължини (FLAGS_TROP).
    Ако use_sidereal=True → изваждаме LAHIRI айанамша ръчно за всички тела.
    Това избягва смесване на режими и ни доближава до секундите.
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

    # Възли (по NODE_TYPE): тропикално + айанамша
    node_id = swe.TRUE_NODE if NODE == "TRUE" else swe.MEAN_NODE
    npos, _ = swe.calc_ut(jd, node_id, FLAGS_TROP)
    trop_rahu = npos[0] % 360.0
    rahu = _sidereal_from_tropical(trop_rahu, ayan) if use_sidereal else trop_rahu
    ketu = (rahu + 180.0) % 360.0

    r_n, r_p = nak_pada(rahu)
    k_n, k_p = nak_pada(ketu)

    # РАХУ и КЕТУ с правилни етикети и 180° разлика
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
    Избягваме TypeError заради различни подписи.
    """
    try:
        if flags is not None:
            # новият подпис
            return swe.houses_ex(jd, flags, lat, lon, hsys)
        else:
            # старият подпис
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
            houses, ascmc = houses_safe(jd, lat, lon, flags=FLAGS_SID, hsys=b'P')
            asc = ascmc[0] % 360.0

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
                pos, _ = swe.calc_ut(jd, pid, FLAGS_SID)
                L = pos[0] % 360.0
                n, p = nak_pada(L)
                res["Planets"].append({
                    "planet": name,
                    "longitude": round(L, 4),
                    "sign": sign_of(L),
                    "nakshatra": n,
                    "pada": p
                })

            node_id = swe.TRUE_NODE if node_is_true else swe.MEAN_NODE
            node_pos, _ = swe.calc_ut(jd, node_id, FLAGS_SID)
            rahu_L = node_pos[0] % 360.0
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
            compute_variant("LAHIRI_TRUE", swe.SIDM_LAHIRI, True),
            compute_variant("LAHIRI_MEAN", swe.SIDM_LAHIRI, False),
            compute_variant("RAMAN_TRUE",  swe.SIDM_RAMAN,  True),
            compute_variant("KP_TRUE",     swe.SIDM_KRISHNAMURTI, True),
        ]

        swe.set_sid_mode(AYAN_MAP.get(AYAN, swe.SIDM_LAHIRI))

        return jsonify({"ok": True, "sidereal_variants": variants}), 200

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

        # Asc (сидерален, Placidus, Lahiri)
        swe.set_sid_mode(AYAN_MAP.get(AYAN, swe.SIDM_LAHIRI))
        houses, ascmc = houses_safe(jd, lat, lon, flags=FLAGS_SID, hsys=b'P')
        asc = ascmc[0] % 360.0

        res = {
            "config": {
                "ayanamsha": AYAN,
                "node_type": NODE,
                "ephe_path": EPHE_PATH,
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
    return f"Astro Calculator API is running (AYAN={AYAN}, NODE={NODE})"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
