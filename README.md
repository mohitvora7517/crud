# Mini Fantasy Cricket App

A Flask web app for your match-based fantasy game with locked teams.

## Features
- User profiles.
- Import a match from Cricsheet (or any public JSON with Cricsheet structure).
- Team submission rules enforced:
  - Exactly 4 players.
  - At least 1 bowler.
  - Exactly 1 MVP (2x points).
  - 1 winning team prediction.
  - Team is locked after submission.
- Scoring:
  - 1 run = 1 point
  - 1 wicket = 25 points
  - Correct winner prediction = 25 points
  - Abandoned/no-result match = 0 points for everyone
- Match leaderboard and tournament leaderboard.

## Data source
This implementation uses **public Cricsheet JSON** as the default source. You can paste a public URL or local path to a JSON file.

## Run
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open: http://localhost:5000

## Example Cricsheet URL
Use a raw JSON URL from Cricsheet downloads (unzipped JSON) or store one locally and reference path.
