import requests
import json
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


def get_activities(token, weeks=8):
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
    return f"{mins}:{secs:02d} /km"


def format_duration(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    if h > 0:
        return f"{h}h {m:02d}m"
    return f"{m}m"


def analyze_and_build_message(activities, athlete):
    runs = [a for a in activities if a.get("type") == "Run"]
    name = athlete.get("firstname", "")
    now = datetime.now()
    weekday_ru = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][now.weekday()]
    date_str = now.strftime(f"{weekday_ru}, %d.%m.%Y")

    if not runs:
        return f"🏃 *Strava Daily Report*\n{date_str}\n\nНет пробежек за последние 8 недель."

    week_start = datetime.now(timezone.utc) - timedelta(days=now.weekday())
    week_runs = [r for r in runs if datetime.fromisoformat(r["start_date"].replace("Z", "+00:00")) >= week_start]
    week_dist = sum(r["distance"] for r in week_runs) / 1000
    week_time = sum(r["moving_time"] for r in week_runs)

    last_week_start = week_start - timedelta(weeks=1)
    last_week_runs = [r for r in runs if last_week_start <= datetime.fromisoformat(r["start_date"].replace("Z", "+00:00")) < week_start]
    last_week_dist = sum(r["distance"] for r in last_week_runs) / 1000

    last_run = runs[0]
    last_dist = last_run["distance"] / 1000
    last_pace = format_pace(last_run.get("average_speed", 0))
    last_hr = last_run.get("average_heartrate")
    last_date = datetime.fromisoformat(last_run["start_date_local"].replace("Z", "")).strftime("%d.%m")

    monthly_dist = sum(r["distance"] for r in runs) / 1000
    avg_weekly = monthly_dist / 8

    recent_runs = [r for r in runs if r.get("average_speed", 0) > 0][:5]
    if len(recent_runs) >= 2:
        paces = [1000 / r["average_speed"] for r in recent_runs]
        pace_trend = "📈 темп улучшается" if paces[0] < paces[-1] else "📉 темп снижается"
    else:
        pace_trend = ""

    if last_week_dist > 0:
        change = ((week_dist - last_week_dist) / last_week_dist) * 100
        change_str = f"+{change:.0f}%" if change >= 0 else f"{change:.0f}%"
    else:
        change_str = "первая неделя"

    lines = [
        f"🏃 *Strava Daily · {date_str}*",
        "",
        f"👟 *Последняя пробежка* ({last_date})",
        f"  {last_dist:.2f} км · {last_pace}" + (f" · ❤️ {last_hr:.0f} bpm" if last_hr else ""),
        "",
        f"📅 *Эта неделя:* {week_dist:.1f} км ({len(week_runs)} пробеж.)",
        f"  vs прошлая неделя: {change_str} ({last_week_dist:.1f} км)",
        "",
        f"📊 *Средний объём:* {avg_weekly:.1f} км/нед (8 нед.)",
    ]
    if pace_trend:
        lines.append(f"  {pace_trend} (последние {len(recent_runs)} пробеж.)")
    lines += ["", "💪 *Продолжай в том же духе!*"]

    return "\n".join(lines)


def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram not configured, printing message:")
        print(message)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    resp = requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    })
    print(f"Telegram: {resp.status_code}")


def main():
    print(f"=== Strava Bot · {datetime.now().isoformat()} ===")
    access_token, _ = refresh_access_token()
    athlete = get_athlete(access_token)
    print(f"Athlete: {athlete.get('firstname')} {athlete.get('lastname')}")
    activities = get_activities(access_token, weeks=8)
    runs = [a for a in activities if a.get("type") == "Run"]
    print(f"Activities: {len(activities)}, runs: {len(runs)}")
    message = analyze_and_build_message(activities, athlete)
    print("Message preview:\n" + message)
    send_telegram(message)
    print("Done!")


if __name__ == "__main__":
    main()
