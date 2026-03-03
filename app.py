from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests
from flask import Flask, flash, g, redirect, render_template, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "fantasy.db"

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    teams = db.relationship("UserTeam", back_populates="user", cascade="all, delete-orphan")


class Match(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    external_match_id = db.Column(db.String(80), unique=True, nullable=False)
    name = db.Column(db.String(255), nullable=False)
    team_a = db.Column(db.String(120), nullable=False)
    team_b = db.Column(db.String(120), nullable=False)
    tournament_name = db.Column(db.String(180), nullable=True)
    starts_at = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(40), nullable=False, default="upcoming")
    winning_team = db.Column(db.String(120), nullable=True)
    is_abandoned = db.Column(db.Boolean, nullable=False, default=False)
    source = db.Column(db.String(40), nullable=False, default="tarun7r")
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    players = db.relationship("MatchPlayer", back_populates="match", cascade="all, delete-orphan")
    player_stats = db.relationship("MatchPlayerStat", back_populates="match", cascade="all, delete-orphan")
    teams = db.relationship("UserTeam", back_populates="match", cascade="all, delete-orphan")


class MatchPlayer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey("match.id"), nullable=False)
    player_name = db.Column(db.String(120), nullable=False)
    team_name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(60), nullable=False, default="unknown")
    is_bowler = db.Column(db.Boolean, nullable=False, default=False)

    match = db.relationship("Match", back_populates="players")


class UserTeam(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    match_id = db.Column(db.Integer, db.ForeignKey("match.id"), nullable=False)
    predicted_winner = db.Column(db.String(120), nullable=False)
    mvp_player_name = db.Column(db.String(120), nullable=False)
    is_locked = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", back_populates="teams")
    match = db.relationship("Match", back_populates="teams")
    picks = db.relationship("TeamPick", back_populates="user_team", cascade="all, delete-orphan")
    score = db.relationship("TeamScore", back_populates="user_team", uselist=False, cascade="all, delete-orphan")

    __table_args__ = (db.UniqueConstraint("user_id", "match_id", name="uq_user_match_team"),)


class TeamPick(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_team_id = db.Column(db.Integer, db.ForeignKey("user_team.id"), nullable=False)
    player_name = db.Column(db.String(120), nullable=False)
    is_bowler = db.Column(db.Boolean, nullable=False)
    is_mvp = db.Column(db.Boolean, nullable=False)

    user_team = db.relationship("UserTeam", back_populates="picks")


class MatchPlayerStat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey("match.id"), nullable=False)
    player_name = db.Column(db.String(120), nullable=False)
    runs = db.Column(db.Integer, nullable=False, default=0)
    wickets = db.Column(db.Integer, nullable=False, default=0)

    match = db.relationship("Match", back_populates="player_stats")


class TeamScore(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_team_id = db.Column(db.Integer, db.ForeignKey("user_team.id"), nullable=False, unique=True)
    points = db.Column(db.Integer, nullable=False, default=0)
    calculated_at = db.Column(db.DateTime, default=datetime.utcnow)

    user_team = db.relationship("UserTeam", back_populates="score")


@dataclass
class PlayerPoints:
    runs: int = 0
    wickets: int = 0


class CricketAPIClient:
    """Adapter for tarun7r/Cricket-API compatible upstreams."""

    def __init__(self) -> None:
        self.base_url = os.environ.get("CRICKET_API_BASE_URL", "https://api.cricapi.com/v1")
        self.api_key = os.environ.get("CRICKET_API_KEY", "")

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        merged = dict(params)
        if self.api_key:
            merged["apikey"] = self.api_key
        url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
        response = requests.get(url, params=merged, timeout=25)
        response.raise_for_status()
        return response.json()

    def list_tournaments(self) -> list[dict[str, str]]:
        payload = self._get("series", {"offset": 0})
        data = payload.get("data", [])
        tournaments = []
        for row in data:
            tournament_id = str(row.get("id") or row.get("seriesId") or "")
            name = row.get("name") or row.get("series") or "Unknown tournament"
            if tournament_id:
                tournaments.append({"id": tournament_id, "name": name})
        return tournaments

    def list_matches_for_tournament(self, tournament_id: str) -> list[dict[str, str]]:
        payload = self._get("series_info", {"id": tournament_id})
        data = payload.get("data", payload)
        groups = data.get("matchList") or data.get("matches") or []
        matches: list[dict[str, str]] = []

        for group in groups:
            items = group.get("matches") if isinstance(group, dict) else None
            if items is None and isinstance(group, dict):
                items = [group]
            for row in items or []:
                match_id = str(row.get("id") or row.get("matchId") or "")
                if not match_id:
                    continue
                teams = row.get("teams") or []
                if len(teams) >= 2:
                    label = f"{teams[0]} vs {teams[1]}"
                else:
                    label = row.get("name") or row.get("matchName") or match_id
                starts_at = row.get("dateTimeGMT") or row.get("date") or ""
                matches.append({"id": match_id, "label": label, "starts_at": starts_at})

        return matches

    def match_info(self, external_match_id: str) -> dict[str, Any]:
        payload = self._get("match_info", {"id": external_match_id})
        data = payload.get("data", payload)

        start_raw = data.get("dateTimeGMT") or data.get("startDate") or datetime.now(UTC).isoformat()
        starts_at = parse_datetime(start_raw)

        teams = data.get("teamInfo") or []
        fallback_teams = data.get("teams", ["Team A", "Team B"])
        team_a = teams[0].get("name") if len(teams) > 0 else fallback_teams[0]
        team_b = teams[1].get("name") if len(teams) > 1 else fallback_teams[1]

        players: list[dict[str, Any]] = []
        for team in teams:
            team_name = team.get("name", "Unknown")
            for p in team.get("players", []):
                role = (p.get("role") or p.get("playingRole") or "unknown").lower()
                players.append(
                    {
                        "name": p.get("name"),
                        "team_name": team_name,
                        "role": role,
                        "is_bowler": "bowler" in role or "allrounder" in role,
                    }
                )

        return {
            "name": data.get("name", f"{team_a} vs {team_b}"),
            "team_a": team_a,
            "team_b": team_b,
            "starts_at": starts_at,
            "status": (data.get("status") or "upcoming").lower(),
            "tournament_name": data.get("series") or data.get("seriesName"),
            "players": [p for p in players if p.get("name")],
        }

    def live_scorecard(self, external_match_id: str) -> dict[str, Any]:
        payload = self._get("match_scorecard", {"id": external_match_id})
        data = payload.get("data", payload)

        outcome = data.get("matchWinner") or data.get("winner")
        status_text = (data.get("status") or "").lower()
        abandoned = "no result" in status_text or "abandon" in status_text or "rain" in status_text

        points_map: dict[str, PlayerPoints] = defaultdict(PlayerPoints)
        for innings in data.get("scorecard", []):
            for batter in innings.get("batting", []):
                name = batter.get("batsman", {}).get("name") or batter.get("name")
                if name:
                    points_map[name].runs += int(batter.get("r") or batter.get("runs") or 0)
            for bowler in innings.get("bowling", []):
                name = bowler.get("bowler", {}).get("name") or bowler.get("name")
                if name:
                    points_map[name].wickets += int(bowler.get("w") or bowler.get("wickets") or 0)

        stats = [{"player_name": p, "runs": s.runs, "wickets": s.wickets} for p, s in points_map.items()]
        return {
            "winning_team": outcome,
            "status": status_text or "live",
            "is_abandoned": abandoned,
            "stats": stats,
        }


def parse_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is not None:
        return parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def calculate_team_score(user_team: UserTeam, match: Match) -> int:
    if match.is_abandoned:
        return 0
    lookup = {row.player_name: (row.runs, row.wickets) for row in match.player_stats}
    total = 0
    for pick in user_team.picks:
        runs, wickets = lookup.get(pick.player_name, (0, 0))
        pts = runs + wickets * 25
        if pick.is_mvp:
            pts *= 2
        total += pts
    if user_team.predicted_winner and user_team.predicted_winner == match.winning_team:
        total += 25
    return total


def recalculate_scores(match: Match) -> None:
    for user_team in match.teams:
        total = calculate_team_score(user_team, match)
        if user_team.score:
            user_team.score.points = total
            user_team.score.calculated_at = datetime.utcnow()
        else:
            db.session.add(TeamScore(user_team_id=user_team.id, points=total))


@app.before_request
def load_current_user() -> None:
    user_id = session.get("user_id")
    g.current_user = User.query.get(user_id) if user_id else None


@app.route("/")
def index():
    matches = Match.query.order_by(Match.starts_at.asc()).all()
    selected_tournament_id = request.args.get("tournament_id", "").strip()
    api = CricketAPIClient()
    tournaments: list[dict[str, str]] = []
    tournament_matches: list[dict[str, str]] = []

    try:
        tournaments = api.list_tournaments()
        if selected_tournament_id:
            tournament_matches = api.list_matches_for_tournament(selected_tournament_id)
    except Exception as exc:
        flash(f"Live tournament list unavailable: {exc}", "error")

    return render_template(
        "index.html",
        matches=matches,
        tournaments=tournaments,
        tournament_matches=tournament_matches,
        selected_tournament_id=selected_tournament_id,
    )


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not name or not email or not password:
            flash("All fields are required.", "error")
            return redirect(url_for("signup"))
        if User.query.filter_by(email=email).first():
            flash("Email already registered.", "error")
            return redirect(url_for("signup"))
        user = User(name=name, email=email, password_hash=generate_password_hash(password))
        db.session.add(user)
        db.session.commit()
        session["user_id"] = user.id
        flash("Account created.", "success")
        return redirect(url_for("index"))
    return render_template("auth.html", mode="signup")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.password_hash, password):
            flash("Invalid credentials.", "error")
            return redirect(url_for("login"))
        session["user_id"] = user.id
        flash("Logged in.", "success")
        return redirect(url_for("index"))
    return render_template("auth.html", mode="login")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Logged out.", "success")
    return redirect(url_for("index"))


@app.route("/matches/import", methods=["POST"])
def import_match():
    external_match_id = request.form.get("external_match_id", "").strip()
    if not external_match_id:
        flash("Please select a match.", "error")
        return redirect(url_for("index"))
    if Match.query.filter_by(external_match_id=external_match_id).first():
        flash("Match already exists.", "error")
        return redirect(url_for("index"))

    api = CricketAPIClient()
    try:
        data = api.match_info(external_match_id)
    except Exception as exc:
        flash(f"Unable to fetch match details: {exc}", "error")
        return redirect(url_for("index"))

    match = Match(
        external_match_id=external_match_id,
        name=data["name"],
        team_a=data["team_a"],
        team_b=data["team_b"],
        starts_at=data["starts_at"],
        status=data["status"],
        tournament_name=data.get("tournament_name"),
    )
    db.session.add(match)
    db.session.flush()

    for p in data["players"]:
        db.session.add(
            MatchPlayer(
                match_id=match.id,
                player_name=p["name"],
                team_name=p["team_name"],
                role=p["role"],
                is_bowler=bool(p["is_bowler"]),
            )
        )

    db.session.commit()
    flash("Match imported with squads.", "success")
    return redirect(url_for("view_match", match_id=match.id))


@app.route("/matches/<int:match_id>")
def view_match(match_id: int):
    match = Match.query.get_or_404(match_id)
    players = MatchPlayer.query.filter_by(match_id=match_id).order_by(MatchPlayer.team_name, MatchPlayer.player_name).all()
    grouped: dict[str, list[MatchPlayer]] = defaultdict(list)
    for player in players:
        grouped[player.team_name].append(player)

    user_team = UserTeam.query.filter_by(user_id=getattr(g.current_user, "id", None), match_id=match_id).first() if g.current_user else None
    can_submit = datetime.utcnow() < match.starts_at and match.status.startswith("upcoming")
    return render_template("match.html", match=match, grouped=grouped, user_team=user_team, can_submit=can_submit)


@app.route("/matches/<int:match_id>/submit", methods=["POST"])
def submit_team(match_id: int):
    if not g.current_user:
        flash("Please log in to submit team.", "error")
        return redirect(url_for("login"))

    match = Match.query.get_or_404(match_id)
    if datetime.utcnow() >= match.starts_at or not match.status.startswith("upcoming"):
        flash("Team submissions are closed for this match.", "error")
        return redirect(url_for("view_match", match_id=match_id))

    if UserTeam.query.filter_by(user_id=g.current_user.id, match_id=match_id).first():
        flash("Your team is already locked.", "error")
        return redirect(url_for("view_match", match_id=match_id))

    selected_players = request.form.getlist("players")
    mvp = request.form.get("mvp", "")
    predicted_winner = request.form.get("predicted_winner", "").strip()

    if len(selected_players) != 4:
        flash("Select exactly 4 players.", "error")
        return redirect(url_for("view_match", match_id=match_id))
    if mvp not in selected_players:
        flash("MVP must be one of your 4 players.", "error")
        return redirect(url_for("view_match", match_id=match_id))

    player_rows = MatchPlayer.query.filter(MatchPlayer.match_id == match_id, MatchPlayer.player_name.in_(selected_players)).all()
    if len(player_rows) != 4:
        flash("Some selected players are invalid.", "error")
        return redirect(url_for("view_match", match_id=match_id))
    if not any(row.is_bowler for row in player_rows):
        flash("At least 1 bowler is required.", "error")
        return redirect(url_for("view_match", match_id=match_id))

    user_team = UserTeam(
        user_id=g.current_user.id,
        match_id=match_id,
        predicted_winner=predicted_winner,
        mvp_player_name=mvp,
        is_locked=True,
    )
    db.session.add(user_team)
    db.session.flush()

    bowlers = {row.player_name for row in player_rows if row.is_bowler}
    for player in selected_players:
        db.session.add(
            TeamPick(
                user_team_id=user_team.id,
                player_name=player,
                is_bowler=player in bowlers,
                is_mvp=(player == mvp),
            )
        )

    db.session.add(TeamScore(user_team_id=user_team.id, points=0))
    db.session.commit()
    flash("Team submitted and locked.", "success")
    return redirect(url_for("view_match", match_id=match_id))


@app.route("/matches/<int:match_id>/sync", methods=["POST"])
def sync_match(match_id: int):
    match = Match.query.get_or_404(match_id)
    api = CricketAPIClient()
    try:
        data = api.live_scorecard(match.external_match_id)
    except Exception as exc:
        flash(f"Unable to sync live score: {exc}", "error")
        return redirect(url_for("view_match", match_id=match_id))

    MatchPlayerStat.query.filter_by(match_id=match.id).delete()
    for row in data["stats"]:
        db.session.add(
            MatchPlayerStat(
                match_id=match.id,
                player_name=row["player_name"],
                runs=row["runs"],
                wickets=row["wickets"],
            )
        )

    match.winning_team = data["winning_team"]
    match.is_abandoned = bool(data["is_abandoned"])
    match.status = data["status"]
    match.updated_at = datetime.utcnow()

    recalculate_scores(match)
    db.session.commit()
    flash("Live data synced and points recalculated.", "success")
    return redirect(url_for("view_match", match_id=match_id))


@app.route("/leaderboard")
def leaderboard():
    rows = []
    for user in User.query.order_by(User.name.asc()).all():
        total = 0
        by_match = []
        for team in user.teams:
            pts = team.score.points if team.score else 0
            total += pts
            by_match.append({"match": team.match.name, "status": team.match.status, "points": pts})
        rows.append({"user": user, "total": total, "matches": by_match})
    rows.sort(key=lambda item: item["total"], reverse=True)
    return render_template("leaderboard.html", rows=rows)


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=5000, debug=True)
