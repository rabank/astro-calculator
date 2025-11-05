import math
from datetime import datetime
from flask import Flask, request, jsonify
import pytz
import swisseph as swe

app = Flask(__name__)

# === Конфигурация: сидерално ЛАХИРИ + TRUE NODE ===
SID_MODE = swe.SE_SIDM_LAHIRI
swe.set_sid_mode(SID_MODE, 0, 0)

# планети, които връщаме (в реда от таблицата ти)
PLANETS = [
    ("Слънце", swe.SE_SUN),
    ("Луна", swe.SE_MOON),
    ("Марс", swe.SE_MARS),
    ("Меркурий", swe.SE_MERCURY),
    ("Юпитер", swe.SE_JUPITER),
    ("Венера", swe.SE_VENUS),
    ("Сатурн", swe.SE_SATURN),
    ("Раху", swe.SE_TRUE_NODE),   # true node
    ("Кету", "KETU"),            # изчисляваме го като Раху + 180°
]

SIGNS_BG = ["Овен","Телец","Близнаци","Рак","Лъв","Дева","Везни","Скорпион","Стрелец","Козирог","Водолей","Риби"]

NAKSHATRAS_BG = [
    "Ашвини","Бхарани","Критика","Рохини","Мригашира","Аридра","Пунарвасу","Пушя","Ашлеша",
    "Магха","Пурва-Пхалгуни","Утара-Пхалгуни","Хаста","Читра","Свати","Вишакха","Анурадха","Джиещха",
    "Мула","Пурва-Ашадха","Утара-Ашадха","Шравана","Дханишта","Шатабхиша","Пурва-Бхадрапада","Утара-Бхадрапада","Ревати"
]

def norm360(x: float) -> float:
    return x % 360.0

def dms_str(x: float) -> str:
    d = int(x)
    m = int((x - d) * 60 + 1e-6)
    s = int((x - d - m/60) * 3600 + 1e-6)
    return f"{d:02d}°{m:02d}′"

def nakshatra_of(long_sid: float):
    # 1 накшатра = 13°20′ = 13 + 20/60 = 13.333333°
    part = 360.0 / 27.0             # 13.333333...
    idx = int(norm360(long_sid) // part)  # 0..26
    within = norm360(long_sid) - idx*part
    pada = int(within // (part/4)) + 1    # 1..4
    return NAKSHATRAS_BG[idx], pada

def to_utc_jd(date_str: str, time_str: str, tz_name: str):
    """
    date: 'YYYY-MM-DD'
    time: 'HH:MM'
    tz: IANA (напр. 'Europe/Sofia')
    -> юлианско време UTC
    """
    tz = pytz.timezone(tz_name)
    local_dt = tz.localize(datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M"))
    utc_dt = local_dt.astimezone(pytz.utc)
    # юлианска дата по UT
    jd = swe.julday(utc_dt.year, utc_dt.month, utc_dt.day, utc_dt.hour + utc_dt.minute/60.0 + utc_dt.second/3600.0)
    return jd, utc_dt

def sidereal_long(body, jd_ut):
    """ сидерална дължина по Лахири (с флага SEFLG_SIDEREAL) """
    flag = swe.SEFLG_SWIEPH | swe.SEFLG_SPEED | swe.SEFLG_SIDEREAL
    if body == "KETU":
        # Кету = Раху + 180°
        rahu = sidereal_long(swe.SE_TRUE_NODE, jd_ut)
        return norm360(rahu + 180.0)
    lon, lat, dist, speed = swe.calc_ut(jd_ut, body, flag)
    return norm360(lon)

def ascendant_sidereal(jd_ut, lat, lon, tz_name):
    """
    Взимаме тропическия Asc от houses(), после го прехвърляме в сидерален като извадим аянамсата за момента.
    Това е стабилен подход за южна карта (D1) и съвпада с повечето джйотиш калкулатори.
    """
    # дома система: Placidus, но за лагната няма значение – взимаме само Asc от резултата
    # houses() очаква географски lon на ИЗТОК положителен -> в swe западът е отрицателен, т.е. стандартно.
    # Функцията връща тропически Asc.
    hsys = b'P'
    ascmc, cusps = swe.houses(jd_ut, lat, lon, hsys)  # ascmc[0] = Asc tropical
    asc_trop = ascmc[0]
    ayan = swe.get_ayanamsa_ut(jd_ut)  # Лахири, защото set_sid_mode е зададен
    asc_sid = norm360(asc_trop - ayan)
    return asc_sid

@app.get("/health")
def health():
    return jsonify({"ok": True})

@app.post("/calculate")
def calculate():
    try:
        data = request.get_json(force=True, silent=True) or {}
        date = data.get("date")      # 'YYYY-MM-DD'
        time = data.get("time")      # 'HH:MM'
        tz   = data.get("timezone") or "UTC"
        lat  = float(data.get("lat"))
        lon  = float(data.get("lon"))

        if not date or not time or math.isnan(lat) or math.isnan(lon):
            return jsonify({"ok": False, "error": "Липсват коректни дата/час/координати."}), 400

        jd_ut, utc_dt = to_utc_jd(date, time, tz)

        # Asc (сидерален)
        asc = ascendant_sidereal(jd_ut, lat, lon, tz)
        asc_sign_idx = int(asc // 30)
        asc_sign = SIGNS_BG[asc_sign_idx]

        # Планети (сидерални дължини Лахири + накшатра/пада)
        planets_out = []
        for name, code in PLANETS:
            lon_sid = sidereal_long(code, jd_ut)
            sign_idx = int(lon_sid // 30)
            sign = SIGNS_BG[sign_idx]
            deg_in_sign = lon_sid % 30.0
            nak, pada = nakshatra_of(lon_sid)
            planets_out.append({
                "planet": name,
                "longitude": round(lon_sid, 6),
                "sign": sign,
                "nakshatra": nak,
                "pada": int(pada),
                "deg_in_sign": round(deg_in_sign, 2),
            })

        payload = {
            "Ascendant": {
                "degree": round(asc, 6),
                "sign": asc_sign
            },
            "Planets": planets_out,
            "timezone": tz
        }
        return jsonify(payload)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

if __name__ == "__main__":
    # локално: python app.py
    app.run(host="0.0.0.0", port=10000)
