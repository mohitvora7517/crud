# Fantasy Cricket Live Web App

A user-friendly Flask app for private fantasy contests with locked 4-player teams, live score sync, and tournament leaderboard.

## What is implemented
- Account system (signup/login/logout).
- Tournament-first import flow (no manual match ID typing):
  - Select tournament from dropdown
  - Select match from that tournament
  - Import selected match and squads
- Team lock rules:
  - Exactly 4 players
  - Minimum 1 bowler (using API role tags)
  - Exactly 1 MVP (2x multiplier)
  - 1 winner prediction
  - No edit after submit
  - Submit only before match starts
- Match page supports both:
  - Team creation from selected match squads
  - Public visibility of all submitted user teams for that match
- Live update button per match:
  - Fetches scorecard
  - Recalculates all submitted team points
- Scoring:
  - 1 run = 1 point
  - 1 wicket = 25 points
  - Correct winner = +25 points
  - Abandoned/no-result/rain-abandoned = 0 points for all teams
- Tournament leaderboard with per-match breakdown.

## API setup
This project uses a client adapter compatible with tarun7r/Cricket-API style data.

```bash
export CRICKET_API_BASE_URL="https://api.cricapi.com/v1"
export CRICKET_API_KEY="your_key"
```

## Run
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open: `http://localhost:5000`
