import requests
import os
from datetime import datetime, timedelta, timezone

# ===== CONFIG FROM ENV VARS =====
CLIENT_ID = os.environ.get("STRAVA_CLIENT_ID", "243960")
CLIENT_SECRET = os.environ.get("STRAVA_CLIENT_SECRET", "aaef164ff706dcb60a6bef981f356f95a7f3dddc")
REFRESH_TOKEN = os.environ.get("STRAVA_REFRESH_TOKEN", "3dc6f44323fef2cb7d4a0dbfbb4ea7ca56e0030d")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

def refresh_access_token():
    resp = requests.post("https://www.strava.com/oauth/token", data={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN,
        "grant_type": "refresh_token"
    })
    data = resp.json()
    return data["access_token"], data["refresh_token"]

def get_activities(token, weeks=52):
    # Берём за год, чтобы видеть все данные для рекордов и понедельной статистики
    after = int((datetime.now(timezone.utc) - timedelta(weeks=weeks)).timestamp())
    headers = {"Authorization": f"Bearer {token}"}
    activities = []
    page = 1
    while True:
        resp = requests.get(
            "https://www.strava.com/api/v3/athlete/activities",
            headers=headers,
            params={"per_page": 100, "page": page, "after": after}
        )
        batch = resp.json()
        if not batch:
            break
        activities.extend(batch)
        page += 1
    # Явная сортировка от новых к старым
    activities.sort(key=lambda a: a.get("start_date", ""), reverse=True)
    return activities

def get_athlete(token):
    headers = {"Authorization": f"Bearer {token}"}
    return requests.get("https://www.strava.com/api/v3/athlete", headers=headers).json()

def format_pace(speed_ms):
    if not speed_ms or speed_ms == 0:
        return "N/A"
    pace_sec = 1000 / speed_ms
    mins = int(pace_sec // 60)
    secs = int(pace_sec % 60)
    return f"{mins}:{secs:02d} /км"

def format_duration(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    if h > 0:
        return f"{h}ч {m:02d}м"
    return f"{m}м"

def get_week_start(dt):
    # Начало недели — понедельник
    return dt - timedelta(days=dt.weekday())

def build_message(activities, athlete):
    runs = [a for a in activities if a.get("type") == "Run"]

    now = datetime.now(timezone.utc).astimezone()
    weekdays_ru = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    weekday_ru = weekdays_ru[now.weekday()]
    date_str = now.strftime(f"{weekday_ru}, %d.%m.%Y")

    if not runs:
        return f"🏃 *Strava Report · {date_str}*\n\nНет пробежек за последний год."

    # Последняя пробежка
    last_run = runs[0]
    last_dist = last_run["distance"] / 1000
    last_pace = format_pace(last_run.get("average_speed", 0))
    last_hr = last_run.get("average_heartrate")
    last_duration = format_duration(last_run.get("moving_time", 0))
    last_date = datetime.fromisoformat(last_run["start_date_local"].replace("Z", "")).strftime("%d.%m")

    # Эта неделя (Пн–сегодня)
    week_start = get_week_start(now.replace(hour=0, minute=0, second=0, microsecond=0))
    week_start_utc = week_start.astimezone(timezone.utc)
    week_runs = [
        r for r in runs
        if datetime.fromisoformat(r["start_date"].replace("Z", "+00:00")) >= week_start_utc
    ]
    week_dist = sum(r["distance"] for r in week_runs) / 1000
    week_time = sum(r["moving_time"] for r in week_runs)
    week_speeds = [r["average_speed"] for r in week_runs if r.get("average_speed", 0) > 0]
    week_avg_pace = format_pace(sum(week_speeds) / len(week_speeds)) if week_speeds else "N/A"
    week_hrs = [r["average_heartrate"] for r in week_runs if r.get("average_heartrate")]
    week_avg_hr = f"{sum(week_hrs)/len(week_hrs):.0f} bpm" if week_hrs else "N/A"

    # Нагрузка недели
    if week_hrs and week_dist > 0:
        avg_hr_val = sum(week_hrs) / len(week_hrs)
        load_str = f"{week_dist * avg_hr_val / 100:.1f} у.е."
    else:
        load_str = "нет данных"

    # Понедельная динамика текущего месяца
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_start_utc = month_start.astimezone(timezone.utc)
    month_runs = [
        r for r in runs
        if datetime.fromisoformat(r["start_date"].replace("Z", "+00:00")) >= month_start_utc
    ]
    month_name_ru = {
        1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
        5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
        9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"
    }[now.month]

    # Разбиваем по неделям внутри месяца
    weekly_stats = {}
    for r in month_runs:
        r_date = datetime.fromisoformat(r["start_date"].replace("Z", "+00:00")).astimezone()
        r_week_start = get_week_start(r_date.replace(hour=0, minute=0, second=0, microsecond=0))
        key = r_week_start.strftime("%d.%m")
        if key not in weekly_stats:
            weekly_stats[key] = {"dist": 0, "speeds": [], "hrs": [], "count": 0, "week_start": r_week_start}
        weekly_stats[key]["dist"] += r["distance"] / 1000
        weekly_stats[key]["count"] += 1
        if r.get("average_speed", 0) > 0:
            weekly_stats[key]["speeds"].append(r["average_speed"])
        if r.get("average_heartrate"):
            weekly_stats[key]["hrs"].append(r["average_heartrate"])

    sorted_weeks = sorted(weekly_stats.items(), key=lambda x: x[1]["week_start"])

    month_lines = []
    for i, (week_key, ws) in enumerate(sorted_weeks, 1):
        w_pace = format_pace(sum(ws["speeds"]) / len(ws["speeds"])) if ws["speeds"] else "N/A"
        w_hr = f"{sum(ws['hrs'])/len(ws['hrs']):.0f} bpm" if ws["hrs"] else "N/A"
        week_end = ws["week_start"] + timedelta(days=6)
        period = f"{ws['week_start'].strftime('%d.%m')}–{week_end.strftime('%d.%m')}"
        month_lines.append(
            f"  Нед {i} ({period}): {ws['dist']:.1f} км · {ws['count']} пробеж. · {w_pace} · ❤️ {w_hr}"
        )

    # Личные рекорды за всё время — по средней скорости на дистанции ±20%
    def pr_for_distance(target_m, tolerance=0.20):
        best = None
        for r in runs:
            dist = r.get("distance", 0)
            speed = r.get("average_speed", 0)
            if speed <= 0 or dist <= 0:
                continue
            lo = target_m * (1 - tolerance)
            hi = target_m * (1 + tolerance)
            if lo <= dist <= hi:
                if best is None or speed > best["speed"]:
                    best = {
                        "speed": speed,
                        "dist": dist,
                        "date": r["start_date_local"][:10]
                    }
        return best

    pr_5k  = pr_for_distance(5000)
    pr_10k = pr_for_distance(10000)
    pr_15k = pr_for_distance(15000)
    pr_16k = pr_for_distance(16000)
    pr_21k = pr_for_distance(21097)  # полумарафон

    def pr_str(pr, label_dist):
        if not pr:
            return "нет данных"
        pace = format_pace(pr["speed"])
        return f"{pace} ({pr['dist']/1000:.2f} км, {pr['date']})"

    pr_5k_str  = pr_str(pr_5k,  "5 км")
    pr_10k_str = pr_str(pr_10k, "10 км")
    pr_15k_str = pr_str(pr_15k, "15 км")
    pr_16k_str = pr_str(pr_16k, "16 км")
    pr_21k_str = pr_str(pr_21k, "21.1 км")

    # Собираем сообщение
    lines = [
        f"🏃‍♀️ *Strava Report · {date_str}*",
        "",
        f"👟 *Последняя пробежка* — {last_date}",
        f"  📏 {last_dist:.2f} км  ⏱ {last_duration}  🐾 {last_pace}" +
        (f"  ❤️ {last_hr:.0f} bpm" if last_hr else ""),
        "",
        f"📅 *Эта неделя* (с {week_start.strftime('%d.%m')})",
        f"  Пробежек: {len(week_runs)}  |  {week_dist:.1f} км  |  {format_duration(week_time)}",
        f"  Средний темп: {week_avg_pace}  |  Средний пульс: {week_avg_hr}",
        f"  Нагрузка: {load_str}",
        "",
        f"📆 *{month_name_ru} — по неделям*",
    ]
    if month_lines:
        lines.extend(month_lines)
    else:
        lines.append("  Пробежек в этом месяце пока нет.")

    lines += [
        "",
        "🏆 *Личные рекорды (за всё время)*",
        f"  5 км:    {pr_5k_str}",
        f"  10 км:   {pr_10k_str}",
        f"  15 км:   {pr_15k_str}",
        f"  16 км:   {pr_16k_str}",
        f"  21.1 км: {pr_21k_str}",
    ]

    return "\n".join(lines)

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    })

def main():
    access_token, _ = refresh_access_token()
    activities = get_activities(access_token, weeks=52)
    athlete = get_athlete(access_token)
    message = build_message(activities, athlete)
    send_telegram(message)
    print("Message sent.")
    print(message)

if __name__ == "__main__":
    main()
