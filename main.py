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
    # ÐÐµÑÑÐ¼ Ð·Ð° Ð³Ð¾Ð´, ÑÑÐ¾Ð±Ñ Ð²Ð¸Ð´ÐµÑÑ Ð²ÑÐµ Ð´Ð°Ð½Ð½ÑÐµ Ð´Ð»Ñ ÑÐµÐºÐ¾ÑÐ´Ð¾Ð² Ð¸ Ð¿Ð¾Ð½ÐµÐ´ÐµÐ»ÑÐ½Ð¾Ð¹ ÑÑÐ°ÑÐ¸ÑÑÐ¸ÐºÐ¸
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
    # Ð¯Ð²Ð½Ð°Ñ ÑÐ¾ÑÑÐ¸ÑÐ¾Ð²ÐºÐ° Ð¾Ñ Ð½Ð¾Ð²ÑÑ Ðº ÑÑÐ°ÑÑÐ¼
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
    return f"{mins}:{secs:02d} /ÐºÐ¼"

def format_duration(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    if h > 0:
        return f"{h}Ñ {m:02d}Ð¼"
    return f"{m}Ð¼"

def get_week_start(dt):
    # ÐÐ°ÑÐ°Ð»Ð¾ Ð½ÐµÐ´ÐµÐ»Ð¸ â Ð¿Ð¾Ð½ÐµÐ´ÐµÐ»ÑÐ½Ð¸Ðº
    return dt - timedelta(days=dt.weekday())

def build_message(activities, athlete):
    runs = [a for a in activities if a.get("type") == "Run"]

    now = datetime.now(timezone.utc).astimezone()
    weekdays_ru = ["ÐÐ½", "ÐÑ", "Ð¡Ñ", "Ð§Ñ", "ÐÑ", "Ð¡Ð±", "ÐÑ"]
    weekday_ru = weekdays_ru[now.weekday()]
    date_str = now.strftime(f"{weekday_ru}, %d.%m.%Y")

    if not runs:
        return f"ð *Strava Report Â· {date_str}*\n\nÐÐµÑ Ð¿ÑÐ¾Ð±ÐµÐ¶ÐµÐº Ð·Ð° Ð¿Ð¾ÑÐ»ÐµÐ´Ð½Ð¸Ð¹ Ð³Ð¾Ð´."

    # ÐÐ¾ÑÐ»ÐµÐ´Ð½ÑÑ Ð¿ÑÐ¾Ð±ÐµÐ¶ÐºÐ°
    last_run = runs[0]
    last_dist = last_run["distance"] / 1000
    last_pace = format_pace(last_run.get("average_speed", 0))
    last_hr = last_run.get("average_heartrate")
    last_duration = format_duration(last_run.get("moving_time", 0))
    last_date = datetime.fromisoformat(last_run["start_date_local"].replace("Z", "")).strftime("%d.%m")

    # Ð­ÑÐ° Ð½ÐµÐ´ÐµÐ»Ñ (ÐÐ½âÑÐµÐ³Ð¾Ð´Ð½Ñ)
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

    # ÐÐ°Ð³ÑÑÐ·ÐºÐ° Ð½ÐµÐ´ÐµÐ»Ð¸
    if week_hrs and week_dist > 0:
        avg_hr_val = sum(week_hrs) / len(week_hrs)
        load_str = f"{week_dist * avg_hr_val / 100:.1f} Ñ.Ðµ."
    else:
        load_str = "Ð½ÐµÑ Ð´Ð°Ð½Ð½ÑÑ"

    # Ð¡Ð°Ð¼Ð°Ñ Ð´Ð»Ð¸Ð½Ð½Ð°Ñ Ð¿ÑÐ¾Ð±ÐµÐ¶ÐºÐ° Ð½ÐµÐ´ÐµÐ»Ð¸
    longest_run = max(week_runs, key=lambda r: r["distance"]) if week_runs else None
    if longest_run:
        lr_dist = longest_run["distance"] / 1000
        lr_pace = format_pace(longest_run.get("average_speed", 0))
        lr_date = datetime.fromisoformat(longest_run["start_date_local"].replace("Z", "")).strftime("%d.%m")
        longest_str = f"{lr_dist:.2f} ÐºÐ¼ Â· {lr_pace} ({lr_date})"
    else:
        longest_str = "Ð½ÐµÑ Ð´Ð°Ð½Ð½ÑÑ"

    # Ð¢ÑÐµÐ½Ð´ ÑÐµÐ¼Ð¿Ð° Ð·Ð° Ð¿Ð¾ÑÐ»ÐµÐ´Ð½Ð¸Ðµ 4 Ð½ÐµÐ´ÐµÐ»Ð¸
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
            pace_trend_parts.append("â")
    # Ð¡ÑÑÐµÐ»ÐºÐ¸ Ð¼ÐµÐ¶Ð´Ñ Ð½ÐµÐ´ÐµÐ»ÑÐ¼Ð¸
    pace_trend_str = ""
    for i, p in enumerate(pace_trend_parts):
        if i > 0:
            # Ð¡ÑÑÐµÐ»ÐºÐ°: ÐµÑÐ»Ð¸ ÑÐµÐ¼Ð¿ ÑÐ»ÑÑÑÐ¸Ð»ÑÑ (ÑÐ¸ÑÑÐ° Ð¼ÐµÐ½ÑÑÐµ) â Ð²Ð²ÐµÑÑ, ÑÑÐ¶Ðµ â Ð²Ð½Ð¸Ð·
            prev = pace_trend_parts[i-1]
            curr = p
            if prev != "â" and curr != "â":
                def pace_to_sec(s):
                    parts = s.replace(" /ÐºÐ¼", "").split(":")
                    return int(parts[0]) * 60 + int(parts[1])
                arrow = " â " if pace_to_sec(curr) <= pace_to_sec(prev) else " â "
                pace_trend_str += arrow + curr
            else:
                pace_trend_str += " â " + curr
        else:
            pace_trend_str = p

    # ÐÑÐ»ÑÑÐ¾Ð²ÑÐµ Ð·Ð¾Ð½Ñ Ð½Ð° Ð¾ÑÐ½Ð¾Ð²Ðµ ÑÑÐµÐ´Ð½ÐµÐ³Ð¾ Ð¿ÑÐ»ÑÑÐ° (Ð¿ÑÐ¸Ð±Ð»Ð¸Ð·Ð¸ÑÐµÐ»ÑÐ½Ð¾, Ð±ÐµÐ· Ð´ÐµÑÐ°Ð»ÑÐ½Ð¾Ð³Ð¾ Ð·Ð°Ð¿ÑÐ¾ÑÐ°)
    # ÐÐ¾Ð½Ñ Ð¿Ð¾ % Ð¾Ñ Ð¼Ð°ÐºÑ Ð¿ÑÐ»ÑÑÐ°: Z1 <60%, Z2 60-70%, Z3 70-80%, Z4 80-90%, Z5 >90%
    # ÐÐ»Ñ Ð±ÐµÐ³ÑÐ½ÑÐ¸ Ð±ÐµÐ· Ð´Ð°Ð½Ð½ÑÑ Ð¾ Ð¼Ð°ÐºÑ Ð¿ÑÐ»ÑÑÐµ Ð¸ÑÐ¿Ð¾Ð»ÑÐ·ÑÐµÐ¼ ÑÐ¾ÑÐ¼ÑÐ»Ñ 220-Ð²Ð¾Ð·ÑÐ°ÑÑ Ð¸Ð»Ð¸ Ð´ÐµÑÐ¾Ð»Ñ 185
    MAX_HR = 185  # Ð¿ÑÐ¸Ð±Ð»Ð¸Ð·Ð¸ÑÐµÐ»ÑÐ½Ð¾
    zone_counts = {"Z1+Z2 (Ð»ÑÐ³ÐºÐ¸Ð¹)": 0, "Z3 (Ð°ÑÑÐ¾Ð±Ð½ÑÐ¹)": 0, "Z4+Z5 (Ð¸Ð½ÑÐµÐ½ÑÐ¸Ð²Ð½ÑÐ¹)": 0}
    zone_total = 0
    for r in week_runs:
        hr = r.get("average_heartrate")
        t = r.get("moving_time", 0)
        if hr and t:
            pct = hr / MAX_HR * 100
            if pct < 70:
                zone_counts["Z1+Z2 (Ð»ÑÐ³ÐºÐ¸Ð¹)"] += t
            elif pct < 80:
                zone_counts["Z3 (Ð°ÑÑÐ¾Ð±Ð½ÑÐ¹)"] += t
            else:
                zone_counts["Z4+Z5 (Ð¸Ð½ÑÐµÐ½ÑÐ¸Ð²Ð½ÑÐ¹)"] += t
            zone_total += t
    if zone_total > 0:
        z_easy = zone_counts["Z1+Z2 (Ð»ÑÐ³ÐºÐ¸Ð¹)"] / zone_total * 100
        z_aero = zone_counts["Z3 (Ð°ÑÑÐ¾Ð±Ð½ÑÐ¹)"] / zone_total * 100
        z_hard = zone_counts["Z4+Z5 (Ð¸Ð½ÑÐµÐ½ÑÐ¸Ð²Ð½ÑÐ¹)"] / zone_total * 100
        zones_str = f"Ð»ÑÐ³ÐºÐ¸Ð¹ {z_easy:.0f}% Â· Ð°ÑÑÐ¾Ð±Ð½ÑÐ¹ {z_aero:.0f}% Â· Ð¸Ð½ÑÐµÐ½ÑÐ¸Ð²Ð½ÑÐ¹ {z_hard:.0f}%"
    else:
        zones_str = "Ð½ÐµÑ Ð´Ð°Ð½Ð½ÑÑ"

    # ÐÐ¾Ð½ÐµÐ´ÐµÐ»ÑÐ½Ð°Ñ Ð´Ð¸Ð½Ð°Ð¼Ð¸ÐºÐ° ÑÐµÐºÑÑÐµÐ³Ð¾ Ð¼ÐµÑÑÑÐ°
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_start_utc = month_start.astimezone(timezone.utc)
    month_runs = [
        r for r in runs
        if datetime.fromisoformat(r["start_date"].replace("Z", "+00:00")) >= month_start_utc
    ]
    month_name_ru = {
        1: "Ð¯Ð½Ð²Ð°ÑÑ", 2: "Ð¤ÐµÐ²ÑÐ°Ð»Ñ", 3: "ÐÐ°ÑÑ", 4: "ÐÐ¿ÑÐµÐ»Ñ",
        5: "ÐÐ°Ð¹", 6: "ÐÑÐ½Ñ", 7: "ÐÑÐ»Ñ", 8: "ÐÐ²Ð³ÑÑÑ",
        9: "Ð¡ÐµÐ½ÑÑÐ±ÑÑ", 10: "ÐÐºÑÑÐ±ÑÑ", 11: "ÐÐ¾ÑÐ±ÑÑ", 12: "ÐÐµÐºÐ°Ð±ÑÑ"
    }[now.month]

    # Ð Ð°Ð·Ð±Ð¸Ð²Ð°ÐµÐ¼ Ð¿Ð¾ Ð½ÐµÐ´ÐµÐ»ÑÐ¼ Ð²Ð½ÑÑÑÐ¸ Ð¼ÐµÑÑÑÐ°
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
        period = f"{ws['week_start'].strftime('%d.%m')}â{week_end.strftime('%d.%m')}"
        month_lines.append(
            f"  ÐÐµÐ´ {i} ({period}): {ws['dist']:.1f} ÐºÐ¼ Â· {ws['count']} Ð¿ÑÐ¾Ð±ÐµÐ¶. Â· {w_pace} Â· â¤ï¸ {w_hr}"
        )

    # Лучшие попытки (топ-3) по дистанции ±20%
    def best_efforts_for_distance(target_m, tolerance=0.20):
        results = []
        lo = target_m * (1 - tolerance)
        hi = target_m * (1 + tolerance)
        for r in runs:
            dist = r.get("distance", 0)
            speed = r.get("average_speed", 0)
            moving_time = r.get("moving_time", 0)
            if speed <= 0 or dist <= 0 or moving_time <= 0:
                continue
            if lo <= dist <= hi:
                results.append({
                    "speed": speed,
                    "dist": dist,
                    "moving_time": moving_time,
                    "date": r["start_date_local"][:10]
                })
        results.sort(key=lambda x: x["speed"], reverse=True)
        return results[:3]

    def format_effort_time(seconds):
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    be_5k  = best_efforts_for_distance(5000)
    be_10k = best_efforts_for_distance(10000)
    be_21k = best_efforts_for_distance(21097)

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


    # Ð¡Ð¾Ð±Ð¸ÑÐ°ÐµÐ¼ ÑÐ¾Ð¾Ð±ÑÐµÐ½Ð¸Ðµ
    lines = [
        f"ðââï¸ *Strava Report Â· {date_str}*",
        "",
        f"ð *ÐÐ¾ÑÐ»ÐµÐ´Ð½ÑÑ Ð¿ÑÐ¾Ð±ÐµÐ¶ÐºÐ°* â {last_date}",
        f"  ð {last_dist:.2f} ÐºÐ¼  â± {last_duration}  ð¾ {last_pace}" +
        (f"  â¤ï¸ {last_hr:.0f} bpm" if last_hr else ""),
        "",
        f"ð *Ð­ÑÐ° Ð½ÐµÐ´ÐµÐ»Ñ* (Ñ {week_start.strftime('%d.%m')})",
        f"  ÐÑÐ¾Ð±ÐµÐ¶ÐµÐº: {len(week_runs)}  |  {week_dist:.1f} ÐºÐ¼  |  {format_duration(week_time)}",
        f"  Ð¡ÑÐµÐ´Ð½Ð¸Ð¹ ÑÐµÐ¼Ð¿: {week_avg_pace}  |  Ð¡ÑÐµÐ´Ð½Ð¸Ð¹ Ð¿ÑÐ»ÑÑ: {week_avg_hr}",
        f"  ÐÐ»Ð¸Ð½Ð½Ð°Ñ: {longest_str}",
        f"  ÐÐ°Ð³ÑÑÐ·ÐºÐ°: {load_str}",
        f"  ÐÑÐ»ÑÑ. Ð·Ð¾Ð½Ñ: {zones_str}",
        "",
        f"ð *{month_name_ru} â Ð¿Ð¾ Ð½ÐµÐ´ÐµÐ»ÑÐ¼*",
    ]
    if month_lines:
        lines.extend(month_lines)
    else:
        lines.append("  ÐÑÐ¾Ð±ÐµÐ¶ÐµÐº Ð² ÑÑÐ¾Ð¼ Ð¼ÐµÑÑÑÐµ Ð¿Ð¾ÐºÐ° Ð½ÐµÑ.")

    lines += [
        "",
        "ð *Ð¢ÑÐµÐ½Ð´ ÑÐµÐ¼Ð¿Ð° (Ð¿Ð¾ÑÐ»ÐµÐ´Ð½Ð¸Ðµ 4 Ð½ÐµÐ´ÐµÐ»Ð¸)*",
        f"  {pace_trend_str}",
        "",
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
    lines += [
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
