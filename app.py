import os
from flask import Flask, request, jsonify
import swisseph as swe
import math
from datetime import datetime

app = Flask(__name__)

# Настройки
swe.set_sid_mode(swe.SIDM_LAHIRI)  # Лахири айанамса

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
    return SIGNS[int(longitude / 30)]

def get_nakshatra(longitude):
    index = int(longitude / (360 / 27))
    pada = int(((longitude % (360 / 27)) / (360 / 108)) + 1)
    return NAKSHATRAS[index], pada

@app.route('/calculate', methods=['POST'])
def calculate():
    data = request.json
    date_str = data.get('date')
    time_str = data.get('time')
    lat = float(data.get('lat'))
    lon = float(data.get('lon'))

    # Конвертиране към Julian Day
    dt = datetime.strptime(date_str + " " + time_str, "%Y-%m-%d %H:%M")
    jd = swe.julday(dt.year, dt.month, dt.day,
                    dt.hour + dt.minute/60.0)

    results = {}

    # Асцендент
    houses, ascmc = swe.houses(jd, lat, lon, b'P')
    asc = ascmc[0] % 360
    results["Ascendant"] = {
        "degree": round(asc, 2),
        "sign": get_sign(asc)
    }

    # Планети
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
        pos, _ = swe.calc_ut(jd, pid)
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

@app.route('/')
def home():
    return "Astro Calculator API is running"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

