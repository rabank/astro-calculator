# --- горе оставаш импортите както са ---
from flask import Flask, request, jsonify
from flask_cors import CORS
import os, math
import swisseph as swe
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=False)

# ===================== Конфиг: АЯНАМША + НОД =====================
# Поддържани айанамши (Swiss Ephemeris):
AYANAMSHA_MAP = {
    "LAHIRI":        swe.SIDM_LAHIRI,         # Chitra (Jagannatha Hora default)
    "RAMAN":         swe.SIDM_RAMAN,          # B.V. Raman
    "KRISHNAMURTI":  swe.SIDM_KRISHNAMURTI,   # KP (Krusnamurti)
    "KP":            swe.SIDM_KRISHNAMURTI,
    "FAGAN_BRADLEY": swe.SIDM_FAGAN_BRADLEY,
    "DELUCE":        swe.SIDM_DELUCE,
    "DJWHAL_KHUL":   swe.SIDM_DJWHAL_KHUL,
    "ALDEBARAN_15TAU": swe.SIDM_ALDEBARAN_15TAU,
    # при нужда добави още от списъка на swe
}

# Чети дефолти от environment (Render -> Environment):
ENV_AYAN = os.environ.get("AYANAMSHA", "LAHIRI").upper()
ENV_NODE = os.environ.get("NODE_TYPE", "MEAN").upper()  # MEAN или TRUE

def _apply_sidereal_mode(chosen: str):
    """Прилага конкретна айанамша към Swiss Ephemeris (sidereal)."""
    sid_mode = AYANAMSHA_MAP.get(chosen, swe.SIDM_LAHIRI)
    swe.set_sid_mode(sid_mode)

def _is_true_node(chosen: str) -> bool:
    return chosen.upper() == "TRUE"

# Първоначално задаваме дефолти от env:
_apply_sidereal_mode(ENV_AYAN)
FLAGS = swe.FLG_SWIEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED

SIGNS = ["Овен","Телец","Близнаци","Рак","Лъв","Дева","Везни",
         "Скорпион","Стрелец","Козирог","Водолей","Риби"]

NAKSHATRAS = ["Ашвини","Бхарани","Криттика","Рохини","Мригашира","Ардра",
              "Пунаравасу","Пушя","Ашлеша","Магха","Пурва-Пхалгуни",
              "Утара-Пхалгуни","Хаста","Читра","Свати","Вишакха","Анурадха",
              "Джиещха","Мула","Пурва-Ашадха","Утара-Ашадха","Шравана",
              "Дханишта","Шатабхиша","Пурва-Бхадра","Утара-Бхадра","Ревати"]

def get_sign(lon): 
    return SIGNS[int((lon % 360) // 30)]

def get_nakshatra(lon):
    span = 360.0 / 27.0
    idx = int((lon % 360) // span)
    pada = int(((lon % span) / (span / 4.0))) + 1
    return NAKSHATRAS[idx], pada

@app.after_request
def add_cors_headers(resp):
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    resp.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    return resp

@app.route('/calculate', methods=['POST', 'OPTIONS'])
def calculate():
    if request.method == 'OPTIONS':
        return ('', 204)

    data = request.get_json(force=True, silent=True) or {}

    # --- локални настройки на заявката (override на env) ---
    req_ayan = (data.get('ayanamsha') or ENV_AYAN).upper()     # напр. "RAMAN"
    req_node = (data.get('node') or ENV_NODE).upper()          # "MEAN" / "TRUE"
    _apply_sidereal_mode(req_ayan)

    # вход
    date_str = data.get('date')      # "YYYY-MM-DD"
    time_str = data.get('time')      # "HH:MM"
    tz_str   = data.get('timezone')  # "Europe/Sofia"
    lat = float(data.get('lat'))
    lon = float(data.get('lon'))

    # локално време -> UTC
    dt_local = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo(tz_str))
    dt_utc   = dt_local.astimezone(timezone.utc)
    ut_hour = dt_utc.hour + dt_utc.minute/60 + dt_utc.second/3600

    jd = swe.julday(dt_utc.year, dt_utc.month, dt_utc.day, ut_hour)

    results = {}

    # Асцендент (Placidus, геоцентрично)
    houses, ascmc = swe.houses_ex(jd, FLAGS, lat, lon, b'P')
    asc = ascmc[0] % 360
    results["Ascendant"] = {"degree": round(asc, 2), "sign": get_sign(asc)}

    # Планети (sidereal)
    planets = [
        (swe.SUN,      "Слънце"),
        (swe.MOON,     "Луна"),
        (swe.MERCURY,  "Меркурий"),
        (swe.VENUS,    "Венера"),
        (swe.MARS,     "Марс"),
        (swe.JUPITER,  "Юпитер"),
        (swe.SATURN,   "Сатурн"),
    ]
    planet_data = []
    for pid, name in planets:
        pos, _ = swe.calc_ut(jd, pid, FLAGS)
        glon = pos[0] % 360
        nak, pada = get_nakshatra(glon)
        planet_data.append({
            "planet": name,
            "longitude": round(glon, 2),
            "sign": get_sign(glon),
            "nakshatra": nak,
            "pada": pada
        })

    # Раху/Кету — избираме Mean или True
    if _is_true_node(req_node):
        node_id = swe.TRUE_NODE
    else:
        node_id = swe.MEAN_NODE

    rahu_pos, _ = swe.calc_ut(jd, node_id, FLAGS)
    rahu_lon = rahu_pos[0] % 360
    nak, pada = get_nakshatra(rahu_lon)
    planet_data.append({"planet": "Раху", "longitude": round(rahu_lon, 2),
                        "sign": get_sign(rahu_lon), "nakshatra": nak, "pada": pada})

    ketu_lon = (rahu_lon + 180.0) % 360
    nak, pada = get_nakshatra(ketu_lon)
    planet_data.append({"planet": "Кету", "longitude": round(ketu_lon, 2),
                        "sign": get_sign(ketu_lon), "nakshatra": nak, "pada": pada})

    results["Planets"] = planet_data
    results["settings"] = {"ayanamsha": req_ayan, "node": req_node}
    return jsonify(results)

@app.route('/')
def home():
    return "Astro Calculator API is running"
if __name__ == '__main__':
    import os
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
