import json, traceback
from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import swisseph as swe
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# ---- Swiss Ephemeris: path to ephemeris files ----
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EPHE_PATH = os.path.join(BASE_DIR, "ephe")
swe.set_ephe_path(EPHE_PATH)

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=False)

# ---------- configuration via ENV ----------
AYAN = os.getenv("AYANAMSHA", "LAHIRI").upper()   # LAHIRI | RAMAN | KP
NODE = os.getenv("NODE_TYPE", "MEAN").upper()     # TRUE | MEAN

AYAN_MAP = {
    "LAHIRI": swe.SIDM_LAHIRI,
    "RAMAN":  swe.SIDM_RAMAN,
    "KP":     swe.SIDM_KRISHNAMURTI,
}
# default Lahiri if unknown
swe.set_sid_mode(AYAN_MAP.get(AYAN, swe.SIDM_LAHIRI))

# ------------------ constants ------------------
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
    return SIGNS[int((lon % 360.0) // 30.0)]

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

# ---- flags ----
# Planets: always tropical, then manual ayanamsha
FLAGS_TROP = swe.FLG_SWIEPH | swe.FLG_SPEED
# we do NOT use SIDEREAL flags here

def _ayanamsha_deg_ut(jd: float) -> float:
    """
    Always compute ayanamsha from Swiss Ephemeris for Lahiri,
    regardless of global AYAN setting (to stay stable vs JHora/Deva).
    """
    swe.set_sid_mode(swe.SIDM_LAHIRI)
    return swe.get_ayanamsa_ut(jd)

def _sidereal_from_tropical(trop_lon: float, ayan: float) -> float:
    return (trop_lon - ayan) % 360.0

def planet_longitudes(jd: float, use_sidereal: bool = True):
    """
    Compute planetary longitudes.
    - First: tropical positions with FLAGS_TROP.
    - If use_sidereal=True: subtract Lahiri ayanamsha manually.
    This avoids mixed modes and keeps consistency with JHora/Deva.
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

    # Nodes (true or mean) from env:
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

def houses_safe(jd, lat, lon, hsys=b'P'):
    """
    Compatibility wrapper for houses_ex / houses across pyswisseph versions.
    Always computes tropical houses; sidereal handled manually.
    """
    try:
        # common signature: houses_ex(jd, lat, lon, hsys)
        return swe.houses_ex(jd, lat, lon, hsys)
    except TypeError:
        try:
            # alternative: houses_ex(jd, flags, lat, lon, hsys)
            return swe.houses_ex(jd, swe.FLG_SWIEPH, lat, lon, hsys)
        except Exception:
            # fallback: classic houses()
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

        jd, _ = dt_to_jd(date_str, time_str, tz_str)

        def compute_variant(label, ayanamsha_const, node_is_true):
            # force specific ayanamsha for this variant
            swe.set_sid_mode(ayanamsha_const)
            ay = swe.get_ayanamsa_ut(jd)

            # Asc: tropical houses → minus this ayanamsha
            houses, ascmc = houses_safe(jd, lat, lon, hsys=b'P')
            asc_trop = ascmc[0] % 360.0
            asc_sid  = (asc_trop - ay) % 360.0

            res = {
                "label": label,
                "Ascendant": {
                    "degree": round(asc_sid, 6),
                    "sign": sign_of(asc_sid)
                },
                "Planets": []
            }

            # 7 planets sidereal for this ayanamsha
            for pid, name in [
                (swe.SUN, "Слънце"), (swe.MOON,"Луна"), (swe.MERCURY,"Меркурий"),
                (swe.VENUS,"Венера"), (swe.MARS,"Марс"),
                (swe.JUPITER,"Юпитер"), (swe.SATURN,"Сатурн")
            ]:
                pos, _ = swe.calc_ut(jd, pid, FLAGS_TROP)
                trop = pos[0] % 360.0
                L = (trop - ay) % 360.0
                n, p = nak_pada(L)
                res["Planets"].append({
                    "planet": name,
                    "longitude": round(L, 6),
                    "sign": sign_of(L),
                    "nakshatra": n,
                    "pada": p
                })

            # Nodes for this variant
            node_id = swe.TRUE_NODE if node_is_true else swe.MEAN_NODE
            node_pos, _ = swe.calc_ut(jd, node_id, FLAGS_TROP)
            rahu_L = (node_pos[0] - ay) % 360.0
            ketu_L = (rahu_L + 180.0) % 360.0
            r_n, r_p = nak_pada(rahu_L)
            k_n, k_p = nak_pada(ketu_L)

            res["Planets"].append({
                "planet": "Раху",
                "longitude": round(rahu_L, 6),
                "sign": sign_of(rahu_L),
                "nakshatra": r_n,
                "pada": r_p
            })
            res["Planets"].append({
                "planet": "Кету",
                "longitude": round(ketu_L, 6),
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

        # restore global
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

        # Julian Date
        jd, _ = dt_to_jd(date_str, time_str, tz_str)

        # Ascendant:
        # 1) tropical houses, Placidus
        houses, ascmc = houses_safe(jd, lat, lon, hsys=b'P')
        asc_trop = ascmc[0] % 360.0

        # 2) sidereal via Lahiri ayanamsha
        ayan = _ayanamsha_deg_ut(jd)
        asc_sid = (asc_trop - ayan) % 360.0

        res = {
            "config": {
                "ayanamsha": AYAN,
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
    return f"Astro Calculator API is running (AYAN={AYAN}, NODE={NODE}, EPHE={EPHE_PATH})"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
