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
    activities.sort(key=lambda a: a.get("start_date", ""), reverse=True)
    return activities

def get_activity_best_efforts(token, activity_id):
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(
        f"https://www.strava.com/api/v3/activities/{activity_id}",
        headers=headers
    )
    data = resp.json()
    return data.get("best_efforts", [])

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
    return dt - timedelta(days=dt.weekday())

def build_message(activities, athlete, token):
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

    # Самая длинная пробежка недели
    longest_run = max(week_runs, key=lambda r: r["distance"]) if week_runs else None
    if longest_run:
        lr_dist = longest_run["distance"] / 1000
        lr_pace = format_pace(longest_run.get("average_speed", 0))
        lr_date = datetime.fromisoformat(longest_run["start_date_local"].replace("Z", "")).strftime("%d.%m")
        longest_str = f"{lr_dist:.2f} км · {lr_pace} ({lr_date})"
    else:
        longest_str = "нет данных"

    # Тренд темпа за последние 4 недели
    pace_trend_parts = []
    for w in range(3, -1, -1):
        ws = get_week_start(now.replace(hour=0, minute=0, second=0, microsecond=0)) - timedelta(weeks=w)
        we = ws + timedelta(days=7)
        ws_utc = ws.astimezone(timezone.utc)
        we_utc = we.astimezone(timezone.utc)
        w_runs = [
            r for r in runs
            if ws_utc <= datetime.fromisoformat(r["start_date"].replace("Z", "+00:00")) < we_utc
        ]
        w_speeds = [r["average_speed"] for r in w_runs if r.get("average_speed", 0) > 0]
        if w_speeds:
            pace_trend_parts.append(format_pace(sum(w_speeds) / len(w_speeds)))
        else:
            pace_trend_parts.append("–")
    # Стрелки между неделями
    pace_trend_str = ""
    for i, p in enumerate(pace_trend_parts):
        if i > 0:
            prev = pace_trend_parts[i-1]
            curr = p
            if prev != "–" and curr != "–":
                def pace_to_sec(s):
                    parts = s.replace(" /км", "").split(":")
                    return int(parts[0]) * 60 + int(parts[1])
                arrow = " ↑ " if pace_to_sec(curr) <= pace_to_sec(prev) else " ↓ "
            else:
                arrow = " → "
            pace_trend_str += arrow + curr
        else:
            pace_trend_str = p

    # Зоны пульса
    MAX_HR = 185
    zone_counts = {"Z1+Z2 (лёгкий)": 0, "Z3 (аэробный)": 0, "Z4+Z5 (интенсивный)": 0}
    zone_total = 0
    for r in week_runs:
        hr = r.get("average_heartrate")
        t = r.get("moving_time", 0)
        if hr and t:
            pct = hr / MAX_HR * 100
            if pct < 70:
                zone_counts["Z1+Z2 (лёгкий)"] += t
            elif pct < 80:
                zone_counts["Z3 (аэробный)"] += t
            else:
                zone_counts["Z4+Z5 (интенсивный)"] += t
            zone_total += t
    if zone_total > 0:
        z_easy = zone_counts["Z1+Z2 (лёгкий)"] / zone_total * 100
        z_aero = zone_counts["Z3 (аэробный)"] / zone_total * 100
        z_hard = zone_counts["Z4+Z5 (интенсивный)"] / zone_total * 100
        zones_str = f"🟢 {z_easy:.0f}% · 🟡 {z_aero:.0f}% · 🔴 {z_hard:.0f}%"
    else:
        zones_str = "нет данных"

    # Статистика по неделям
    weekly_stats = {}
    for r in runs:
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
            f"  Нед {i} ({period}): {ws['dist']:.1f} км · {ws['count']} проб. · {w_pace} · ❤️ {w_hr}"
        )

    # Лучшие попытки (топ-3) через Strava best_efforts API
    def get_best_efforts_all(target_name, runs_list, token_val):
        results = []
        for r in runs_list:
            activity_id = r.get("id")
            if not activity_id:
                continue
            best_efforts = get_activity_best_efforts(token_val, activity_id)
            for be in best_efforts:
                if be.get("name") == target_name:
                    results.append({
                        "moving_time": be["elapsed_time"],
                        "dist": be["distance"],
                        "speed": be["distance"] / be["elapsed_time"] if be["elapsed_time"] > 0 else 0,
                        "date": r["start_date_local"][:10]
                    })
        results.sort(key=lambda x: x["moving_time"])
        return results[:3]

    def format_effort_time(seconds):
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    be_5k  = get_best_efforts_all("5k", runs, token)
    be_10k = get_best_efforts_all("10k", runs, token)
    be_21k = get_best_efforts_all("Half-Marathon", runs, token)

    medals = ["🥇", "🥈", "🥉"]

    def format_efforts_block(efforts):
        if not efforts:
            return ["  нет данных"]
        result = []
        for i, e in enumerate(efforts):
            medal = medals[i] if i < len(medals) else f"{i+1}."
            t = format_effort_time(e["moving_time"])
            pace = format_pace(e["speed"])
            d_km = e["dist"] / 1000
            d_date = e["date"]
            result.append(f"  {medal} {t}  {pace}  ({d_km:.2f} км, {d_date})")
        return result

    # Собираем сообщение
    lines = [
        f"🏃‍♀️ *Strava Report · {date_str}*",
        "",
        f"🔵 *Последняя пробежка* — {last_date}",
        f"  📍 {last_dist:.2f} км  ⏱ {last_duration}  💟 {last_pace}" +
        (f"  ❤️ {last_hr:.0f} bpm" if last_hr else ""),
        "",
        f"📅 *Эта неделя* (с {week_start.strftime('%d.%m')})",
        f"  Пробежек: {len(week_runs)}  |  {week_dist:.1f} км  |  {format_duration(week_time)}",
        f"  Ср. темп: {week_avg_pace}  |  Ср. пульс: {week_avg_hr}",
        f"  Длиннейшая: {longest_str}",
        f"  Нагрузка: {load_str}",
        f"  Зоны пульса: {zones_str}",
        "",
        f"📊 *Статистика по неделям*",
    ]
    if month_lines:
        lines.extend(month_lines)
    else:
        lines.append("  Нет данных")

    lines += [
        "",
        f"📈 *Динамика темпа (последние 4 недели)*",
        f"  {pace_trend_str}",
        "",
        "🏅 *Лучшие попытки*",
        "  *5 км:*",
    ]
    lines.extend(format_efforts_block(be_5k))
    lines += [
        "  *10 км:*",
    ]
    lines.extend(format_efforts_block(be_10k))
    lines += [
        "  *21.1 км:*",
    ]
    lines.extend(format_efforts_block(be_21k))

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
    message = build_message(activities, athlete, access_token)
    send_telegram(message)
    print("Message sent.")
    print(message)

if __name__ == "__main__":
    main()
