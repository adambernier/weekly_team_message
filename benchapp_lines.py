#!/usr/bin/env python3
"""Screenshot the proposed lines from BenchApp for the next Wobblin Goblins game."""

import argparse
import os
import sys

from playwright.sync_api import sync_playwright

BENCHAPP_URL = "https://www.benchapp.com/"
EMAIL = os.environ.get("BENCHAPP_EMAIL")
PASSWORD = os.environ.get("BENCHAPP_PASSWORD")
DEFAULT_OUTPUT = "lines.png"


def login(page, debug=False):
    page.goto(BENCHAPP_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)

    if debug:
        print(f"DEBUG title: {page.title()!r}  url: {page.url!r}", file=sys.stderr)

    # Homepage loads first — click the Login nav link to reach the login form
    login_link = page.query_selector('a:has-text("Login"), a:has-text("Log in"), a:has-text("Sign in")')
    if login_link:
        login_link.click()
        page.wait_for_timeout(3000)
        if debug:
            print(f"DEBUG after clicking Login — url: {page.url!r}", file=sys.stderr)

    # Search the main frame and any iframes for the login fields
    email_field, pw_field, submit, target_frame = None, None, None, None
    for frame in [page] + page.frames[1:]:
        email_field = frame.query_selector(
            'input[type="email"], input[type="text"], input[name="email"], input[placeholder*="email" i]'
        )
        pw_field = frame.query_selector('input[type="password"]')
        if email_field and pw_field:
            submit = frame.query_selector('button[type="submit"], input[type="submit"], button:has-text("Log In")')
            target_frame = frame
            break

    if debug:
        all_inputs = page.evaluate("() => [...document.querySelectorAll('input')].map(i => ({type: i.type, name: i.name, id: i.id}))")
        print(f"DEBUG inputs on main frame: {all_inputs}", file=sys.stderr)
        print(f"DEBUG frames: {[f.url for f in page.frames]}", file=sys.stderr)
        print(f"DEBUG found fields in frame: {target_frame is not None}", file=sys.stderr)

    if not email_field or not pw_field:
        if debug:
            _dump_page(page, "debug_pre_login.png")
        raise RuntimeError("Could not find login fields")

    email_field.fill(EMAIL)
    pw_field.fill(PASSWORD)

    if not submit:
        raise RuntimeError("Could not find submit button")
    submit.click()
    page.wait_for_timeout(5000)

    _dismiss_modal(page, debug)

    if debug:
        print(f"DEBUG after login — title: {page.title()!r}  url: {page.url!r}", file=sys.stderr)
        _dump_page(page, "debug_after_login.png")


def _dismiss_modal(page, debug=False):
    """Dismiss the 'what's new' modal if present."""
    try:
        page.locator('text="Continue"').first.click(timeout=3000)
        if debug:
            print("DEBUG clicked Continue button", file=sys.stderr)
        page.wait_for_timeout(2000)
    except Exception as e:
        if debug:
            print(f"DEBUG no Continue button found ({e})", file=sys.stderr)


def find_lines_and_screenshot(page, output_path, debug=False):
    """Navigate to the lines view for the next game and screenshot it."""
    if debug:
        _dump_links(page, "after login")

    # Switch to the Goblins team
    page.goto("https://www.benchapp.com/team-switcher", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(5000)
    if debug:
        _dump_links(page, "team switcher")
        _dump_page(page, "debug_team_switcher.png")

    page.get_by_text('Goblins', exact=True).last.click()
    page.wait_for_timeout(3000)

    # Navigate to home now that Goblins is the active team
    page.goto("https://www.benchapp.com/", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)
    _dismiss_modal(page, debug)

    if debug:
        print(f"DEBUG after switching to Goblins — url: {page.url!r}", file=sys.stderr)
        _dump_links(page, "after switching to Goblins")
        _dump_page(page, "debug_after_home.png")

    # Click the "Up Next" game card on the home page using JS —
    # find any clickable element containing a time (H:MM) and not "FINAL"
    result = page.evaluate("""
        () => {
            const candidates = [
                ...document.querySelectorAll('a, button, [role="button"], [tabindex="0"]')
            ];
            for (const el of candidates) {
                const text = (el.innerText || el.textContent || '').trim();
                if (!text.includes('FINAL') &&
                    /\\d:\\d\\d/.test(text)) {
                    el.click();
                    return text.substring(0, 120);
                }
            }
            return null;
        }
    """)
    if debug:
        print(f"DEBUG clicked game card: {result!r}", file=sys.stderr)
    page.wait_for_timeout(3000)

    if debug:
        print(f"DEBUG after clicking game — url: {page.url!r}", file=sys.stderr)
        _dump_links(page, "after clicking game")
        _dump_page(page, "debug_after_game.png")

    # Click the "lines" tab on the game detail page
    try:
        page.locator('text="lines"').first.click(timeout=5000)
        page.wait_for_timeout(3000)
        if debug:
            print(f"DEBUG after clicking lines tab — url: {page.url!r}", file=sys.stderr)
    except Exception:
        print("No lines have been set.", file=sys.stderr)
        sys.exit(0)

    # Override CSS to allow player names to wrap instead of truncate
    page.add_style_tag(content="""
        * { white-space: normal !important; }
    """)
    page.wait_for_timeout(500)

    # Crop out the right "Drag Players Into Position" panel if present
    clip_width = page.viewport_size["width"]
    drag_panel = page.get_by_text("Drag Players Into Position").first.bounding_box()
    if drag_panel:
        clip_width = int(drag_panel["x"])

    page.screenshot(path=output_path, clip={
        "x": 0, "y": 0,
        "width": clip_width,
        "height": page.viewport_size["height"],
    })

    print(output_path)


def _dump_links(page, label):
    links = page.evaluate("""
        () => [...document.querySelectorAll('a[href], button')]
            .map(el => el.innerText.trim())
            .filter(t => t.length > 0 && t.length < 60)
            .slice(0, 40)
    """)
    print(f"DEBUG links/buttons [{label}]: {links}", file=sys.stderr)


def _dump_page(page, filename):
    page.screenshot(path=filename, full_page=True)
    print(f"DEBUG screenshot saved: {filename}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Screenshot BenchApp lines for the next game"
    )
    parser.add_argument(
        "-o", "--output",
        default=DEFAULT_OUTPUT,
        help=f"Output PNG file (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Dump page structure and save intermediate screenshots",
    )
    args = parser.parse_args()

    if not EMAIL or not PASSWORD:
        print(
            "Error: BENCHAPP_EMAIL and BENCHAPP_PASSWORD must be set.",
            file=sys.stderr,
        )
        sys.exit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1920, "height": 900})
            login(page, debug=args.debug)
            find_lines_and_screenshot(page, args.output, debug=args.debug)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
