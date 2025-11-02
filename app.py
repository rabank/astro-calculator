from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import swisseph as swe
from datetime import datetime
from zoneinfo import ZoneInfo  # стандартна библиотека за часови зони (Python 3.9+)

# --- Сидерална система (Джьотиш) с Лахири айанамса ---
swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)
FLAGS = swe.FLG_SWIEPH | swe.FLG_SIDEREAL

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=False)

@app.after_request
def add_cors_headers(resp):
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    resp.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    return resp

SIGNS = [
    "Овен", "Телец", "Близнаци", "Рак", "Лъв", "Дева",
    "Везни", "Скорпион", "Стрелец", "Козирог", "Водолей", "Риби"
]

NAKSHATRAS = [
    "Ашвини", "Бхарани", "Криттика", "Рохини", "Мригашира",
    "Ардра", "Пунаравасу", "Пушя", "Ашлеша", "Магха",
    "Пурва-Пхалгуни", "Утара-Пхалгуни", "Хаста", "Читра", "Свати",
    "Вишакха", "Анурадха", "Джиещха", "Мула", "Пурва-Ашадха",
    "Утара-Ашадха", "Шравана", "Дханишта", "Шатабхиша", "Пурва-Бхадра",
    "Утара-Бхадра", "Ревати"
]

def get_sign(longitude):
    return SIGNS[int(longitude // 30) % 12]

def get_nakshatra(longitude):
    step = 360.0 / 27.0
    index = int((longitude % 360) // step) % 27
    pada  = int(((longitude % step) / (step / 4.0)) + 1)
    return NAKSHATRAS[index], pada

@app.route('/calculate', methods=['POST', 'OPTIONS'])
def calculate():
    if request.method == 'OPTIONS':
        return ('', 204)  # preflight

    try:
        data = request.json or {}
        date_str = data.get('date')       # "YYYY-MM-DD"
        time_str = data.get('time')       # "HH:MM"
        tz_name  = data.get('timezone')   # напр. "Europe/Sofia"
        lat = float(data.get('lat'))
        lon = float(data.get('lon'))

        if not (date_str and time_str and tz_name):
            return jsonify({"error": "Липсва дата/час/часова зона"}), 400

        # 1) Локален час с посочената часова зона
        dt_local = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo(tz_name))
        # 2) Преобразуваме в UTC
        dt_utc = dt_local.astimezone(ZoneInfo("UTC"))

        # 3) Джулиански ден (UTC)
        ut_hour = dt_utc.hour + dt_utc.minute/60.0 + dt_utc.second/3600.0
        jd = swe.julday(dt_utc.year, dt_utc.month, dt_utc.day, ut_hour)

        results = {}

        # Асцендент – сидерално (важно: с FLAGS)
        houses, ascmc = swe.houses_ex(jd, FLAGS, lat, lon, b'P')
        asc = ascmc[0] % 360
        results["Ascendant"] = {
            "degree": round(asc, 2),
            "sign": get_sign(asc)
        }

        # Планети (True Node; ако в Jataka е Mean Node, ще сменим)
        planets = [
            (swe.SUN, "Слънце"),
            (swe.MOON, "Луна"),
            (swe.MERCURY, "Меркурий"),
            (swe.VENUS, "Венера"),
            (swe.MARS, "Марс"),
            (swe.JUPITER, "Юпитер"),
            (swe.SATURN, "Сатурн"),
            (swe.TRUE_NODE, "Раху")
        ]

        planet_data = []
        for pid, name in planets:
            pos, _ = swe.calc_ut(jd, pid, FLAGS)  # сидерално
            long = pos[0] % 360
            nak, pada = get_nakshatra(long)
            planet_data.append({
                "planet": name,
                "longitude": round(long, 2),
                "sign": get_sign(long),
                "nakshatra": nak,
                "pada": pada
            })

        results["Planets"] = planet_data
        return jsonify(results)

    except Exception as e:
        # Вместо 500 ще видиш ясна причина
        return jsonify({"error": str(e)}), 400

@app.route('/')
def home():
    return "Astro Calculator API is running"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))


