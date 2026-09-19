#!/usr/bin/env python3
"""Generate a team message for the Wobblin Goblins' next game."""

import argparse
import os
import re
import subprocess
import sys
import time
from datetime import date, datetime

from playwright.sync_api import sync_playwright

TEAM_NAME = "Wobblin Goblins"
# The league site spells our team "Woblin Goblins" (single 'b'), so accept any of
# these spellings when matching a scraped name against ours.
TEAM_NAME_VARIANTS = ("Wobblin Goblins", "Woblin Goblins")
LOGIN_URL = "https://apps.daysmartrecreation.com/dash/x/tspc/login"
TEAM_URL = "https://apps.daysmartrecreation.com/dash/x/tspc/teams/10757"

EMAIL = os.environ.get("DAYSMART_EMAIL")
PASSWORD = os.environ.get("DAYSMART_PASSWORD")


def wait_through_queue(page, timeout_minutes=45):
    """If we hit the Cloudflare waiting room, sit still until it clears.

    The waiting room page reloads itself every ~21 seconds via its own JS,
    which maintains queue position via cookie. We just poll the title and wait.
    """
    deadline = time.time() + timeout_minutes * 60
    while time.time() < deadline:
        if "Waiting Room" not in page.title():
            return
        try:
            h2 = page.query_selector("h2")
            if h2:
                print(f"[queue] {h2.inner_text().strip()}", file=sys.stderr)
        except Exception:
            pass
        page.wait_for_timeout(30_000)
    raise RuntimeError(f"Timed out after {timeout_minutes} min in Cloudflare queue")


def login(page):
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
    wait_through_queue(page)
    page.wait_for_timeout(5000)

    email_field = page.query_selector('input[type="text"]')
    pw_field = page.query_selector('input[type="password"]')
    if not email_field or not pw_field:
        raise RuntimeError("Could not find login fields")

    email_field.fill(EMAIL)
    pw_field.fill(PASSWORD)

    submit = page.query_selector('button[type="submit"]')
    if not submit:
        raise RuntimeError("Could not find submit button")
    submit.click()
    page.wait_for_timeout(5000)

    # Verify if login succeeded
    error_el = page.query_selector(".alert-error, .messenger-message-inner")
    if error_el:
        error_text = error_el.inner_text().strip()
        raise RuntimeError(f"Login failed: {error_text}")
    if "login" in page.url:
        raise RuntimeError("Login failed: Still on the login page after submit.")


def get_icon_sibling_text(item, icon_class):
    """Find an icon by class and return the text in the sibling flex-grow-1 div."""
    icon = item.query_selector(f"i.{icon_class}")
    if not icon:
        return ""
    flex_div = icon.evaluate_handle("el => el.closest('.d-flex')").as_element()
    if not flex_div:
        return ""
    text_div = flex_div.query_selector(".flex-grow-1")
    return text_div.inner_text().strip() if text_div else ""


def get_team_name(item, icon_class):
    """Get team name from the parent div of the given icon."""
    icon = item.query_selector(f"i.{icon_class}")
    if not icon:
        return ""
    parent_div = icon.evaluate_handle("el => el.parentElement").as_element()
    if not parent_div:
        return ""
    return parent_div.inner_text().strip()


def parse_game_date(date_str):
    """Parse M/D/YYYY to a date object, or None on failure."""
    try:
        return datetime.strptime(date_str.strip(), "%m/%d/%Y").date()
    except ValueError:
        return None


def parse_time(time_str):
    """Parse '5:30pm' or '10:15 PM' to a datetime."""
    cleaned = time_str.strip().lower().replace(" ", "")
    return datetime.strptime(cleaned, "%I:%M%p")


def format_gametime(time_str):
    """Format time string to '10:15pm' style (no leading zero, lowercase am/pm)."""
    try:
        dt = parse_time(time_str)
        return dt.strftime("%-I:%M%p").lower()
    except ValueError:
        return time_str.strip()


def game_time_phrase(game_date, start_time):
    """Return a natural phrase like 'tonight', 'tomorrow night', or 'Saturday night'."""
    today = date.today()
    delta = (game_date - today).days
    tod = time_of_day(start_time)

    if delta == 0:
        return "tonight" if tod in ("evening", "night") else f"this {tod}"
    elif delta == 1 and today.weekday() == 4:  # Friday → "tomorrow night"
        return f"tomorrow {tod}"
    else:
        return f"{game_date.strftime('%A')} {tod}"


def time_of_day(time_str):
    """Return 'morning', 'afternoon', 'evening', or 'night' for a time string."""
    try:
        hour = parse_time(time_str).hour
        if hour < 12:
            return "morning"
        elif hour < 17:
            return "afternoon"
        elif hour < 20:
            return "evening"
        else:
            return "night"
    except ValueError:
        return ""


def extract_rink_name(location):
    """Extract just the rink portion from 'Venue - Rink Name' style strings."""
    if " - " in location:
        return location.split(" - ")[-1]
    return location


def extract_locker_room_number(location):
    """Extract room number from a location string like 'Venue - LR 10'."""
    m = re.search(r"\bLR\s+(\d+[A-Za-z]?)", location, re.IGNORECASE)
    return m.group(1) if m else None


def normalize_team_name(name):
    """Lowercase a team name and drop everything that isn't a letter."""
    return re.sub(r"[^a-z]", "", name.lower())


def is_our_team(name):
    """Return True if a scraped team name refers to the Wobblin Goblins.

    Compares on the normalized form so case, punctuation, and the league site's
    one-'b' spelling don't matter.
    """
    normalized = normalize_team_name(name)
    if not normalized:
        return False
    return any(normalize_team_name(v) in normalized for v in TEAM_NAME_VARIANTS)


def scrape_next_game(page, debug=False):
    """Load team page, collect game and locker room events, return the next game."""
    page.goto(TEAM_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(8000)

    today = date.today()
    items = page.query_selector_all("dash-event-list-group-item")

    games = {}   # date -> game info dict
    lockers = {} # date -> locker room number string

    for item in items:
        date_str = get_icon_sibling_text(item, "fa-calendar")
        game_date = parse_game_date(date_str)
        if game_date is None or game_date < today:
            continue

        home = get_team_name(item, "fa-home")
        away = get_team_name(item, "fa-circle")
        location = get_icon_sibling_text(item, "fa-map-marker-alt")
        time_raw = get_icon_sibling_text(item, "fa-clock")

        if home or away:
            # Game event — keep the earliest one per date
            if game_date not in games:
                games[game_date] = {
                    "date": game_date,
                    "home": home,
                    "away": away,
                    "time_raw": time_raw,
                    "location": location,
                }
        elif "locker room" in item.inner_text().lower():
            # Locker room event — extract number from location (e.g. "... - LR 10")
            lr_num = extract_locker_room_number(location)
            if lr_num:
                lockers[game_date] = lr_num
            elif debug:
                print(f"DEBUG locker room event found but no LR number in location: {location!r}", file=sys.stderr)

    if not games:
        return None

    next_date = min(games.keys())
    next_game = games[next_date]
    next_game["is_home"] = is_our_team(next_game["home"])
    if not next_game["is_home"] and not is_our_team(next_game["away"]):
        # Don't quietly report "away team" for a game we can't match.
        print(
            f"Warning: could not find {TEAM_NAME} in "
            f"{next_game['home']!r} vs {next_game['away']!r}; assuming away team.",
            file=sys.stderr,
        )
    next_game["locker_room"] = lockers.get(next_date)

    if debug:
        print(f"DEBUG games found on dates: {sorted(games.keys())}", file=sys.stderr)
        print(f"DEBUG locker rooms by date: {lockers}", file=sys.stderr)

    return next_game


def compose_message(game):
    """Compose the team message string."""
    time_raw = game["time_raw"]
    start_time = time_raw.split(" - ")[0] if " - " in time_raw else time_raw

    gametime = format_gametime(start_time)
    phrase = game_time_phrase(game["date"], start_time)
    rink = extract_rink_name(game["location"])
    jersey = "home team, green jerseys" if game["is_home"] else "away team, white jerseys"

    lines = [
        f"gametime {phrase}: {gametime}",
        f"on {rink}",
    ]

    locker = game.get("locker_room")
    lines.append(f"locker room {locker}" if locker else "locker room TBD")
    lines.append(jersey)

    return "\n".join(lines)


def _capture_lines_screenshot(debug=False):
    """Run benchapp_lines.py to refresh lines.png."""
    benchapp_email = os.environ.get("BENCHAPP_EMAIL")
    benchapp_password = os.environ.get("BENCHAPP_PASSWORD")
    if not benchapp_email or not benchapp_password:
        print("Skipping lines screenshot: BENCHAPP_EMAIL / BENCHAPP_PASSWORD not set.", file=sys.stderr)
        return

    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "benchapp_lines.py")
    cmd = [sys.executable, script]
    if debug:
        cmd.append("--debug")

    result = subprocess.run(cmd, capture_output=True, text=True)
    lines_path = result.stdout.strip()
    if result.returncode == 0 and lines_path and os.path.isfile(lines_path):
        print(f"Lines screenshot saved: {lines_path}", file=sys.stderr)
    elif "No lines have been set" in result.stderr:
        print("Lines: not yet set in BenchApp.", file=sys.stderr)
    else:
        detail = result.stderr.strip() or "No screenshot file was produced."
        print(f"Lines screenshot failed:\n{detail}", file=sys.stderr)

    if debug and result.stderr:
        print(result.stderr, file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Generate team message for next Wobblin Goblins game"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Dump detail page icons/info to stderr for troubleshooting",
    )
    parser.add_argument(
        "--no-lines",
        action="store_true",
        help="Skip the BenchApp lines screenshot",
    )
    args = parser.parse_args()

    if not EMAIL or not PASSWORD:
        print(
            "Error: DAYSMART_EMAIL and DAYSMART_PASSWORD environment variables must be set.",
            file=sys.stderr,
        )
        sys.exit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            login(page)
            game = scrape_next_game(page, debug=args.debug)
            if not game:
                print("No upcoming games found.", file=sys.stderr)
                sys.exit(1)
            print(compose_message(game))
        finally:
            browser.close()

    if not args.no_lines:
        _capture_lines_screenshot(debug=args.debug)


if __name__ == "__main__":
    main()
