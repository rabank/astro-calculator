from flask import Flask, request, jsonify
from flask_cors import CORS
import os, math
import swisseph as swe
swe.set_sid_mode(swe.SIDM_LAHIRI)
from datetime import datetime, timezone
from zoneinfo import ZoneInfo  # за работа с IANA timezones, напр. "Europe/Sofia"

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=False)

# Сидерична система: Лахири
swe.set_sid_mode(swe.SIDM_LAHIRI)
FLAGS = swe.FLG_SWIEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED

SIGNS = ["Овен","Телец","Близнаци","Рак","Лъв","Дева","Везни","Скорпион","Стрелец","Козирог","Водолей","Риби"]
NAKSHATRAS = ["Ашвини","Бхарани","Криттика","Рохини","Мригашира","Ардра","Пунаравасу","Пушя","Ашлеша","Магха",
              "Пурва-Пхалгуни","Утара-Пхалгуни","Хаста","Читра","Свати","Вишакха","Анурадха","Джиещха","Мула",
              "Пурва-Ашадха","Утара-Ашадха","Шравана","Дханишта","Шатабхиша","Пурва-Бхадра","Утара-Бхадра","Ревати"]

def get_sign(lon): 
    return SIGNS[int(lon // 30)]

def get_nakshatra(lon):
    idx = int(lon // (360/27))
    pada = int(((lon % (360/27)) / (360/108))) + 1
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

    data = request.json

    # 1) Локална дата/час + IANA timezone -> UTC
    date_str = data.get('date')      # "YYYY-MM-DD"
    time_str = data.get('time')      # "HH:MM"
    tz_str   = data.get('timezone')  # "Europe/Sofia" (задължително)
    lat = float(data.get('lat'))
    lon = float(data.get('lon'))

    dt_local = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo(tz_str))
    dt_utc   = dt_local.astimezone(timezone.utc)

    ut_hour = dt_utc.hour + dt_utc.minute/60 + dt_utc.second/3600
    jd = swe.julday(dt_utc.year, dt_utc.month, dt_utc.day, ut_hour)

    results = {}

    # 2) Асцендент (геоцентрично)
    houses, ascmc = swe.houses_ex(jd, FLAGS, lat, lon, b'P')
    asc = ascmc[0] % 360
    results["Ascendant"] = {"degree": round(asc, 2), "sign": get_sign(asc)}

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

    planet_data = []
    for pid, name in planets:
        pos, _ = swe.calc_ut(jd, pid, FLAGS)
        lon = pos[0] % 360
        nak, pada = get_nakshatra(lon)
        planet_data.append({"planet": name, "longitude": round(lon, 2), "sign": get_sign(lon), "nakshatra": nak, "pada": pada})

    rahu_pos, _ = swe.calc_ut(jd, swe.MEAN_NODE, FLAGS)  # МЕАН НОДЕ
    rahu_lon = rahu_pos[0] % 360
    nak, pada = get_nakshatra(rahu_lon)
    planet_data.append({"planet": "Раху", "longitude": round(rahu_lon, 2), "sign": get_sign(rahu_lon), "nakshatra": nak, "pada": pada})

    ketu_lon = (rahu_lon + 180) % 360
    nak, pada = get_nakshatra(ketu_lon)
    planet_data.append({"planet": "Кету", "longitude": round(ketu_lon, 2), "sign": get_sign(ketu_lon), "nakshatra": nak, "pada": pada})

    results["Planets"] = planet_data
    return jsonify(results)

@app.route('/')
def home():
    return "Astro Calculator API is running"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
