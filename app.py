# app.py
import json, traceback
from flask import Flask, request, jsonify
from flask_cors import CORS
import os, math
import swisseph as swe
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

app = Flask(__name__)
# 1) Много кратък health чек
@app.route('/health', methods=['GET'])
def health():
    return jsonify(ok=True), 200


# 2) Диагностичен /debug – връща няколко варианта (Лахири/Раман/KP и true/mean node)
@app.route('/debug', methods=['GET'])
def debug():
    try:
        # ТЕСТОВИ ВХОД (можеш да ги смениш при нужда)
        date_str = "1988-05-24"
        time_str = "12:00"
        tz_str   = "Europe/Sofia"
        lat      = 43.2141
        lon      = 27.9147

        # локално -> UTC
        dt_local = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo(tz_str))
        dt_utc   = dt_local.astimezone(timezone.utc)
        ut_hour  = dt_utc.hour + dt_utc.minute/60 + dt_utc.second/3600
        jd       = swe.julday(dt_utc.year, dt_utc.month, dt_utc.day, ut_hour)

        def compute_variant(label, ayanamsha_const, node_is_true):
            swe.set_sid_mode(ayanamsha_const)

            # Асцендент
            houses, ascmc = swe.houses_ex(jd, FLAGS, lat, lon, b'P')
            asc = ascmc[0] % 360.0
            res = {
                "label": label,
                "Ascendant": {"degree": round(asc, 2), "sign": SIGNS[int(asc // 30)]},
                "Planets": []
            }

            # 7-те планети
            for pid, name in [
                (swe.SUN, "Слънце"), (swe.MOON,"Луна"), (swe.MERCURY,"Меркурий"),
                (swe.VENUS,"Венера"), (swe.MARS,"Марс"), (swe.JUPITER,"Юпитер"), (swe.SATURN,"Сатурн")
            ]:
                pos, _ = swe.calc_ut(jd, pid, FLAGS)
                L = pos[0] % 360.0
                idx = int(L // (360/27))
                pada = int(((L % (360/27)) / (360/108))) + 1
                res["Planets"].append({
                    "planet": name,
                    "longitude": round(L, 2),
                    "sign": SIGNS[int(L // 30)],
                    "nakshatra": NAKSHATRAS[idx],
                    "pada": pada
                })

            # Раху (true/mean)
            node_id = swe.TRUE_NODE if node_is_true else swe.MEAN_NODE
            node_pos, _ = swe.calc_ut(jd, node_id, FLAGS)
            rahu_L = node_pos[0] % 360.0
            idx = int(rahu_L // (360/27))
            pada = int(((rahu_L % (360/27)) / (360/108))) + 1
            res["Planets"].append({
                "planet": "Раху",
                "longitude": round(rahu_L, 2),
                "sign": SIGNS[int(rahu_L // 30)],
                "nakshatra": NAKSHATRAS[idx],
                "pada": pada
            })

            # Кету = Раху + 180°
            ketu_L = (rahu_L + 180.0) % 360.0
            idx = int(ketu_L // (360/27))
            pada = int(((ketu_L % (360/27)) / (360/108))) + 1
            res["Planets"].append({
                "planet": "Кету",
                "longitude": round(ketu_L, 2),
                "sign": SIGNS[int(ketu_L // 30)],
                "nakshatra": NAKSHATRAS[idx],
                "pada": pada
            })
            return res

        variants = [
            compute_variant("LAHIRI_TRUE", swe.SIDM_LAHIRI, True),
            compute_variant("LAHIRI_MEAN", swe.SIDM_LAHIRI, False),
            compute_variant("RAMAN_TRUE",  swe.SIDM_RAMAN,  True),
            compute_variant("KP_TRUE",     swe.SIDM_KP,     True),
        ]

        return jsonify({"ok": True, "sidereal_variants": variants}), 200

    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 200
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=False)

# ---------- конфигурация през ENV ----------
AYAN = os.getenv("AYANAMSHA", "LAHIRI").upper()   # LAHIRI | RAMAN | KP
NODE = os.getenv("NODE_TYPE", "TRUE").upper()     # TRUE | MEAN

AYAN_MAP = {
    "LAHIRI": swe.SIDM_LAHIRI,      # Chitrapaksha
    "RAMAN":  swe.SIDM_RAMAN,
    "KP":     swe.SIDM_KRISHNAMURTI
}
# по подразбиране – LAHIRI, ако е нещо друго
swe.set_sid_mode(AYAN_MAP.get(AYAN, swe.SIDM_LAHIRI))

# Флагове (геоцентрични, сидерал, true ecliptic-of-date + скорост)
# Заб.: FLG_TRUEPOS/FLG_NONUT/FLG_EQUATORIAL са за фини настройки.
FLAGS_SID = swe.FLG_SWIEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED            # sidereal
FLAGS_TROP = swe.FLG_SWIEPH | swe.FLG_SPEED                               # tropical

SIGNS = ["Овен","Телец","Близнаци","Рак","Лъв","Дева","Везни","Скорпион","Стрелец","Козирог","Водолей","Риби"]
NAK = [
    "Ашвини","Бхарани","Криттика","Рохини","Мригашира","Ардра","Пунаравасу","Пушя","Ашлеша","Магха",
    "Пурва-Пхалгуни","Утара-Пхалгуни","Хаста","Читра","Свати","Вишакха","Анурадха","Джиещха","Мула",
    "Пурва-Ашадха","Утара-Ашадха","Шравана","Дханишта","Шатабхиша","Пурва-Бхадра","Утара-Бхадра","Ревати"
]

def sign_of(lon):
    return SIGNS[int((lon % 360)//30)]

def nak_pada(lon):
    span = 360/27.0
    idx = int((lon % 360) // span)
    pada = int(((lon % span) / (span/4.0))) + 1
    return NAK[idx], pada

def dt_to_jd(date_str, time_str, tz_str):
    dt_local = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo(tz_str))
    dt_utc   = dt_local.astimezone(timezone.utc)
    ut_hour  = dt_utc.hour + dt_utc.minute/60 + dt_utc.second/3600
    jd       = swe.julday(dt_utc.year, dt_utc.month, dt_utc.day, ut_hour)   # UT
    return jd, dt_utc

def planet_longitudes(jd, flags):
    """Връща абсолютна дължина [0..360) за основните планети + node (според NODE)."""
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
        pos, _ = swe.calc_ut(jd, pid, flags)
        lon = pos[0] % 360.0
        n,p = nak_pada(lon)
        out.append({"planet": name, "longitude": round(lon, 6), "sign": sign_of(lon), "nakshatra": n, "pada": p})

    # node
    node_id = swe.TRUE_NODE if NODE == "TRUE" else swe.MEAN_NODE
    npos, _ = swe.calc_ut(jd, node_id, flags)
    nlon = npos[0] % 360.0
    nname = "Раху"   # Кету = +180
    n_nak, n_pada = nak_pada(nlon)
    out.append({"planet": nname, "longitude": round(nlon, 6), "sign": sign_of(nlon), "nakshatra": n_nak, "pada": n_pada})

    # Ketu
    k = (nlon + 180.0) % 360.0
    k_nak, k_pada = nak_pada(k)
    out.append({"planet": "Кету", "longitude": round(k, 6), "sign": sign_of(k), "nakshatra": k_nak, "pada": k_pada})

    return out

@app.after_request
def add_cors(resp):
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    resp.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    return resp

@app.route('/calculate', methods=['POST','OPTIONS'])
def calculate():
    if request.method == 'OPTIONS':
        return ('', 204)

    data = request.get_json(force=True)
    date_str = data.get('date')
    time_str = data.get('time')
    tz_str   = data.get('timezone')
    lat = float(data.get('lat'))
    lon = float(data.get('lon'))

    # Asc (sidereal, placidus)
    jd, dt_utc = dt_to_jd(date_str, time_str, tz_str)
    houses, ascmc = swe.houses_ex(jd, FLAGS_SID, lat, lon, b'P')  # sidereal houses
    asc = ascmc[0] % 360.0

    res = {
        "config": {
            "ayanamsha": AYAN,
            "node_type": NODE,
            "flags_sid": int(FLAGS_SID),
            "flags_trop": int(FLAGS_TROP)
        },
        "Ascendant": {"degree": round(asc, 6), "sign": sign_of(asc)},
        "Planets": planet_longitudes(jd, FLAGS_SID)  # sidereal по текущите опции
    }
    return jsonify(res)

# ---- Диагностика: връща какво точно смята бекендът за tropical/sidereal/разни айанамши/true-mean node ----
@app.route('/debug', methods=['POST'])
def debug():
    data = request.get_json(force=True)
    jd, _ = dt_to_jd(data['date'], data['time'], data['timezone'])

    out = {}
    # tropical
    out['tropical'] = planet_longitudes(jd, FLAGS_TROP)
    # текущите глобални sidereal (AYAN, NODE)
    out['sidereal_current'] = planet_longitudes(jd, FLAGS_SID)

    # сравнение по айанамши (все с TRUE node за да е консистентно)
    save = swe.get_ayanamsa_ex(jd)[0]  # not strictly needed; SwissEphemeris keeps mode global
    for key, mode in AYAN_MAP.items():
        swe.set_sid_mode(mode)
        out[f"sidereal_{key}_TRUE"] = planet_longitudes(jd, swe.FLG_SWIEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED)
    # върни пак в първоначалната
    swe.set_sid_mode(AYAN_MAP.get(AYAN, swe.SIDM_LAHIRI))

    return jsonify(out)

@app.route('/')
def home():
    return f"Astro Calculator API is running (AYAN={AYAN}, NODE={NODE})"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
