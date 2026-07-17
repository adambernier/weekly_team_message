# Weekly Team Message Generator

This project automatically scrapes the upcoming game schedule and locker room assignments for the **Wobblin Goblins** from DaySmart Recreation, and captures the lineup/lines screenshot from BenchApp.

It generates a clean text message block summarizing the game details and places the lines screenshot at `lines.png`, which can be sent directly to the team.

## Features

- **DaySmart Scraper:** Logs in, navigates to the Wobblin Goblins team schedule page, and extracts details of the next upcoming game (date, time, rink, locker room, and home/away jersey colors).
- **BenchApp Scraper:** Logs in, switches to the Goblins team, navigates to the upcoming game lineup, and captures a cropped screenshot of the lines to `lines.png`.
- **Validation:** Performs robust error validation during login to catch outdated passwords or issues immediately.

---

## Setup & Installation

### 1. Prerequisite
Ensure Python 3.8+ is installed on your system.

### 2. Set Up Virtual Environment
Initialize a virtual environment to manage dependencies locally:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies
Install Python libraries and the Playwright headless browser package:
```bash
pip install -r requirements.txt
playwright install chromium
```

### 4. Environment Variables Configuration
The scripts require your credentials to be exposed as environment variables. Add the following exports to your shell configuration (e.g., `~/.bashrc` or `.env` file):

```bash
# DaySmart Recreation Credentials
export DAYSMART_EMAIL="your_email@gmail.com"
export DAYSMART_PASSWORD="your_daysmart_password"

# BenchApp Credentials
export BENCHAPP_EMAIL="your_email@gmail.com"
export BENCHAPP_PASSWORD="your_benchapp_password"
```

---

## Usage

Run the main script to output the next game details and refresh `lines.png`:
```bash
# Activate virtual environment if not already activated
source .venv/bin/activate

# Run the script
python team_message.py
```

### Script Arguments

* `--debug`: Runs in verbose mode, capturing step-by-step logs and intermediate screenshots (like `debug_*.png`) for troubleshooting.
* `--no-lines`: Runs only the DaySmart scraper to generate the text message block, skipping the BenchApp lines screenshot.

---

## Automated scheduled runs
To run this automatically every week on a schedule, you can set it up as a cron job on your system or run it via a GitHub Actions workflow using **GitHub Secrets** to secure your credentials.
