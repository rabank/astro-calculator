# app.py
import json, traceback
from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import swisseph as swe
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=False)

# ---------- конфигурация през ENV ----------
AYAN = os.getenv("AYANAMSHA", "LAHIRI").upper()   # LAHIRI | RAMAN | KP
NODE = os.getenv("NODE_TYPE", "MEAN").upper()     # TRUE | MEAN  (по подразбиране MEAN)


AYAN_MAP = {
    "LAHIRI": swe.SIDM_LAHIRI,      # Chitrapaksha
    "RAMAN":  swe.SIDM_RAMAN,
    "KP":     swe.SIDM_KRISHNAMURTI
}
# по подразбиране – LAHIRI, ако е нещо друго
swe.set_sid_mode(AYAN_MAP.get(AYAN, swe.SIDM_LAHIRI))

# ------------------ константи/помощни ------------------
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
    span = 360/27.0
    idx = int((lon % 360) // span)
    pada = int(((lon % span) / (span/4.0))) + 1
    return NAK[idx], pada

def dt_to_jd(date_str: str, time_str: str, tz_str: str):
    dt_local = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo(tz_str))
    dt_utc   = dt_local.astimezone(timezone.utc)
    ut_hour  = dt_utc.hour + dt_utc.minute/60 + dt_utc.second/3600
    jd       = swe.julday(dt_utc.year, dt_utc.month, dt_utc.day, ut_hour)   # UT
    return jd, dt_utc

# ---- Флагове: смятаме планетите само тропикално, после вадим айанамша ръчно ----
FLAGS_TROP = swe.FLG_SWIEPH | swe.FLG_SPEED | swe.FLG_TRUEPOS
# За къщите/диагностика можем да ползваме сидерален флаг (не за планети!)
FLAGS_SID  = swe.FLG_SWIEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED

def _ayanamsha_deg_ut(jd: float) -> float:
    # игнорира ENV и винаги ползва ЛАХИРИ, за да елиминираме източници на грешка
    swe.set_sid_mode(swe.SIDM_LAHIRI)
    return swe.get_ayanamsa_ut(jd)

def _sidereal_from_tropical(trop_lon: float, ayan: float) -> float:
    return (trop_lon - ayan) % 360.0

def planet_longitudes(jd: float, use_sidereal: bool = True):
    """
    Винаги смятаме тропикални дължини, после ако use_sidereal=True
    изваждаме айанамшата РЪЧНО за всички тела. Така няма смесване на режими.
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
        pos, _ = swe.calc_ut(jd, pid, FLAGS_TROP)  # винаги тропикално
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

    # Възли (true/mean) – също тропикално и после айанамша
    node_id = swe.TRUE_NODE if NODE == "TRUE" else swe.MEAN_NODE
    npos, _ = swe.calc_ut(jd, node_id, FLAGS_TROP)
    trop_rahu = npos[0] % 360.0
    rahu = _sidereal_from_tropical(trop_rahu, ayan) if use_sidereal else trop_rahu
    ketu = (rahu + 180.0) % 360.0

    k_n, k_p = nak_pada(ketu)
    r_n, r_p = nak_pada(rahu)

    # Първо Кету, после Раху
    # Правилни етикети
    out.append({"planet":"Раху", "longitude":round(rahu,6),"sign":sign_of(rahu), "nakshatra":r_n, "pada":r_p})
    out.append({"planet":"Кету", "longitude":round(ketu,6),"sign":sign_of(ketu), "nakshatra":k_n, "pada":k_p})

    return out

@app.after_request
def add_cors(resp):
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    resp.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    return resp
def houses_safe(jd, lat, lon, flags=None, hsys=b'P'):
    """
    Връща (cusps, ascmc) и работи с и без FLAGS параметър,
    според версията на pyswisseph.
    """
    try:
        if flags is None:
            # опит 1: старият подпис без flags
            return swe.houses_ex(jd, lat, lon, hsys)
        else:
            # опит 2: новият подпис с flags
            return swe.houses_ex(jd, flags, lat, lon, hsys)
    except TypeError:
        # ако сме уцелили „грешния“ подпис – пробваме другия
        try:
            return swe.houses_ex(jd, lat, lon, hsys)
        except Exception:
            # краен fallback – класическата функция без „ex“
            cusps, ascmc = swe.houses(jd, lat, lon, hsys)
            return (cusps, ascmc)

# 1) Много кратък health чек
@app.route('/health', methods=['GET'])
def health():
    return jsonify(ok=True), 200

# 2) Единствен диагностичен /debug (GET) – пробва няколко айанамши и true/mean node
@app.route('/debug', methods=['GET'], endpoint='nk_debug')
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

            # Асцендент (сидерални къщи)
            # БЕШЕ: houses, ascmc = swe.houses_ex(jd, FLAGS_SID, lat, lon, b'P')
            houses, ascmc = houses_safe(jd, lat, lon, flags=FLAGS_SID, hsys=b'P')
            asc = ascmc[0] % 360.0

            res = {
                "label": label,
                "Ascendant": {"degree": round(asc, 2), "sign": SIGNS[int(asc // 30)]},
                "Planets": []
            }

            # 7-те планети (тук за дебъг ползваме сидералния флаг)
            for pid, name in [
                (swe.SUN, "Слънце"), (swe.MOON,"Луна"), (swe.MERCURY,"Меркурий"),
                (swe.VENUS,"Венера"), (swe.MARS,"Марс"), (swe.JUPITER,"Юпитер"), (swe.SATURN,"Сатурн")
            ]:
                pos, _ = swe.calc_ut(jd, pid, FLAGS_SID)
                L = pos[0] % 360.0
                idx = int(L // (360/27))
                pada = int(((L % (360/27)) / (360/108))) + 1
                res["Planets"].append({
                    "planet": name,
                    "longitude": round(L, 2),
                    "sign": SIGNS[int(L // 30)],
                    "nakshatra": NAK[idx],
                    "pada": pada
                })

            # Раху (true/mean)
            node_id = swe.TRUE_NODE if node_is_true else swe.MEAN_NODE
            node_pos, _ = swe.calc_ut(jd, node_id, FLAGS_SID)
            rahu_L = node_pos[0] % 360.0
            idx = int(rahu_L // (360/27))
            pada = int(((rahu_L % (360/27)) / (360/108))) + 1
            res["Planets"].append({
                "planet": "Раху",
                "longitude": round(rahu_L, 2),
                "sign": SIGNS[int(rahu_L // 30)],
                "nakshatra": NAK[idx],
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
                "nakshatra": NAK[idx],
                "pada": pada
            })
            return res

        variants = [
            compute_variant("LAHIRI_TRUE", swe.SIDM_LAHIRI, True),
            compute_variant("LAHIRI_MEAN", swe.SIDM_LAHIRI, False),
            compute_variant("RAMAN_TRUE",  swe.SIDM_RAMAN,  True),
            compute_variant("KP_TRUE",     swe.SIDM_KRISHNAMURTI, True),
        ]

        # върни глобалната айанамша обратно към конфигурираната
        swe.set_sid_mode(AYAN_MAP.get(AYAN, swe.SIDM_LAHIRI))

        return jsonify({"ok": True, "sidereal_variants": variants}), 200

    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 200

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

        # JD
        jd, _ = dt_to_jd(date_str, time_str, tz_str)

        # Сидерален Ascendant (Placidus)
        swe.set_sid_mode(AYAN_MAP.get(AYAN, swe.SIDM_LAHIRI))
        # БЕШЕ: houses, ascmc = swe.houses_ex(jd, FLAGS_SID, lat, lon, b'P')
        houses, ascmc = houses_safe(jd, lat, lon, flags=FLAGS_SID, hsys=b'P')
        asc = ascmc[0] % 360.0

        res = {
            "config": {
                "ayanamsha": AYAN,
                "node_type": NODE,
            },
            "Ascendant": {"degree": round(asc, 6), "sign": sign_of(asc)},
            "Planets": planet_longitudes(jd, use_sidereal=True)
        }
        return jsonify(res), 200

    except Exception as e:
        # върни чист JSON вместо HTML 500
        return jsonify({
            "ok": False,
            "error": str(e),
            "trace": traceback.format_exc()
        }), 500

@app.route('/diag', methods=['GET'])
def diag():
    date_str, time_str, tz_str = "1988-05-24", "12:00", "Europe/Sofia"
    jd, _ = dt_to_jd(date_str, time_str, tz_str)

    # тропикално Слънце
    trop_sun, _ = swe.calc_ut(jd, swe.SUN, FLAGS_TROP)
    trop = trop_sun[0] % 360.0

    swe.set_sid_mode(swe.SIDM_LAHIRI)
    ay = swe.get_ayanamsa_ut(jd)
    sid = (trop - ay) % 360.0

    return jsonify({
        "mode_forced": "LAHIRI",
        "tropical_sun_deg": trop,
        "ayanamsha_deg": ay,
        "sidereal_sun_deg": sid,
        "sidereal_sun_in_sign_deg": sid % 30.0
    })
@app.route('/')
def home():
    return f"Astro Calculator API is running (AYAN={AYAN}, NODE={NODE})"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
