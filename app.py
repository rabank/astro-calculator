from flask import Flask, request, jsonify
from flask_cors import CORS
import os, math
import swisseph as swe
from datetime import datetime, timezone
from zoneinfo import ZoneInfo  # IANA timezones, напр. "Europe/Sofia"

# --- Flask ---
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=False)

# --- Swiss Ephemeris (сидерично Лахири) ---
swe.set_sid_mode(swe.SIDM_LAHIRI)
FLAGS = swe.FLG_SWIEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED

SIGNS = [
    "Овен","Телец","Близнаци","Рак","Лъв","Дева",
    "Везни","Скорпион","Стрелец","Козирог","Водолей","Риби"
]
NAKSHATRAS = [
    "Ашвини","Бхарани","Криттика","Рохини","Мригашира","Ардра",
    "Пунаравасу","Пушя","Ашлеша","Магха","Пурва-Пхалгуни","Утара-Пхалгуни",
    "Хаста","Читра","Свати","Вишакха","Анурадха","Джиещха","Мула",
    "Пурва-Ашадха","Утара-Ашадха","Шравана","Дханишта","Шатабхиша",
    "Пурва-Бхадра","Утара-Бхадра","Ревати"
]

def get_sign(lon):
    return SIGNS[int(lon // 30)]

def get_nakshatra(lon):
    step = 360.0 / 27.0            # 13°20'
    idx = int(lon // step)
    pada = int(((lon % step) / (step / 4.0))) + 1
    return NAKSHATRAS[idx], pada

@app.get("/health")
def health():
    return jsonify(ok=True)

@app.post('/calculate')
def calculate():
    data = request.get_json(force=True)

    # 1) Локална дата/час + IANA timezone -> UTC
    date_str = data.get('date')      # "YYYY-MM-DD"
    time_str = data.get('time')      # "HH:MM"
    tz_str   = data.get('timezone')  # "Europe/Sofia"
    lat = float(data.get('lat'))
    lon = float(data.get('lon'))

    dt_local = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo(tz_str))
    dt_utc   = dt_local.astimezone(timezone.utc)

    ut_hour = dt_utc.hour + dt_utc.minute/60.0 + dt_utc.second/3600.0
    jd = swe.julday(dt_utc.year, dt_utc.month, dt_utc.day, ut_hour)

    out = {}

    # 2) Асцендент (геоцентрично), южен стил не влияе на изчислението
    houses, ascmc = swe.houses_ex(jd, FLAGS, lat, lon, b'P')
    asc = ascmc[0] % 360.0
    out["Ascendant"] = {"degree": round(asc, 2), "sign": get_sign(asc)}

    # 3) Планети (Mean Node за Раху; Кету = Раху + 180°)
    planets = [
        (swe.SUN,      "Слънце"),
        (swe.MOON,     "Луна"),
        (swe.MERCURY,  "Меркурий"),
        (swe.VENUS,    "Венера"),
        (swe.MARS,     "Марс"),
        (swe.JUPITER,  "Юпитер"),
        (swe.SATURN,   "Сатурн"),
    ]

    plist = []
    for pid, name in planets:
        pos, _ = swe.calc_ut(jd, pid, FLAGS)
        lon_ecl = pos[0] % 360.0
        nak, pada = get_nakshatra(lon_ecl)
        plist.append({
            "planet": name,
            "longitude": round(lon_ecl, 2),
            "sign": get_sign(lon_ecl),
            "nakshatra": nak,
            "pada": pada
        })

    # Раху = MEAN_NODE (исканият от теб модел)
    rahu_pos, _ = swe.calc_ut(jd, swe.MEAN_NODE, FLAGS)
    rahu_lon = rahu_pos[0] % 360.0
    nak, pada = get_nakshatra(rahu_lon)
    plist.append({"planet": "Раху", "longitude": round(rahu_lon, 2), "sign": get_sign(rahu_lon), "nakshatra": nak, "pada": pada})

    ketu_lon = (rahu_lon + 180.0) % 360.0
    nak, pada = get_nakshatra(ketu_lon)
    plist.append({"planet": "Кету", "longitude": round(ketu_lon, 2), "sign": get_sign(ketu_lon), "nakshatra": nak, "pada": pada})

    out["Planets"] = plist
    return jsonify(out)

@app.get('/')
def home():
    return "Astro Calculator API is running"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
