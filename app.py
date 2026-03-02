from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from flask import Flask, flash, redirect, render_template, request, url_for
from flask_sqlalchemy import SQLAlchemy

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "fantasy.db"

app = Flask(__name__)
app.config["SECRET_KEY"] = "dev-secret-key"
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    teams = db.relationship("UserTeam", back_populates="user", cascade="all, delete-orphan")


class Match(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    external_match_id = db.Column(db.String(80), unique=True, nullable=False)
    name = db.Column(db.String(255), nullable=False)
    source = db.Column(db.String(40), nullable=False, default="cricsheet")
    winning_team = db.Column(db.String(120), nullable=True)
    is_abandoned = db.Column(db.Boolean, nullable=False, default=False)
    parsed_at = db.Column(db.DateTime, default=datetime.utcnow)
    teams = db.relationship("UserTeam", back_populates="match", cascade="all, delete-orphan")
    player_stats = db.relationship("MatchPlayerStat", back_populates="match", cascade="all, delete-orphan")


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


def parse_cricsheet_match(payload: dict[str, Any]) -> dict[str, Any]:
    info = payload.get("info", {})
    match_name = info.get("event", {}).get("name") or f"{info.get('teams', ['Team A','Team B'])[0]} vs {info.get('teams', ['Team A','Team B'])[1]}"

    outcome = info.get("outcome", {})
    winner = outcome.get("winner")
    abandoned = bool(outcome.get("result") == "no result")

    players_by_team = info.get("players", {})
    bowlers = set()
    for team_players in players_by_team.values():
        for p in team_players:
            if any(k in p.lower() for k in ["bowler", "spinner"]):
                bowlers.add(p)

    points_map: dict[str, PlayerPoints] = defaultdict(PlayerPoints)

    for innings in payload.get("innings", []):
        innings_data = next(iter(innings.values()))
        for over in innings_data.get("overs", []):
            for delivery in over.get("deliveries", []):
                batter = delivery.get("batter")
                runs = delivery.get("runs", {}).get("batter", 0)
                if batter:
                    points_map[batter].runs += int(runs)

                wickets = delivery.get("wickets", [])
                for wicket in wickets:
                    kind = wicket.get("kind", "")
                    if kind and kind not in {"run out", "retired hurt", "obstructing the field"}:
                        bowler = delivery.get("bowler")
                        if bowler:
                            points_map[bowler].wickets += 1
                            bowlers.add(bowler)

    player_stats = [
        {"player_name": player, "runs": stats.runs, "wickets": stats.wickets}
        for player, stats in points_map.items()
    ]

    return {
        "name": match_name,
        "winning_team": winner,
        "is_abandoned": abandoned,
        "bowlers": sorted(list(bowlers)),
        "player_stats": player_stats,
        "teams": info.get("teams", []),
    }


def load_json_from_source(source_url: str) -> dict[str, Any]:
    if source_url.startswith("http"):
        response = requests.get(source_url, timeout=30)
        response.raise_for_status()
        return response.json()

    with open(source_url, "r", encoding="utf-8") as f:
        return json.load(f)


def calculate_team_score(user_team: UserTeam, match: Match) -> int:
    if match.is_abandoned:
        return 0

    stats_lookup = {
        stat.player_name: (stat.runs, stat.wickets)
        for stat in match.player_stats
    }

    total = 0
    for pick in user_team.picks:
        runs, wickets = stats_lookup.get(pick.player_name, (0, 0))
        player_points = runs + (wickets * 25)
        if pick.is_mvp:
            player_points *= 2
        total += player_points

    if user_team.predicted_winner == match.winning_team:
        total += 25

    return total


@app.route("/")
def index():
    matches = Match.query.order_by(Match.parsed_at.desc()).all()
    users = User.query.order_by(User.name.asc()).all()
    return render_template("index.html", matches=matches, users=users)


@app.route("/users", methods=["POST"])
def create_user():
    name = request.form.get("name", "").strip()
    if not name:
        flash("Name is required", "error")
        return redirect(url_for("index"))

    existing = User.query.filter_by(name=name).first()
    if existing:
        flash("User already exists", "error")
    else:
        db.session.add(User(name=name))
        db.session.commit()
        flash("User created", "success")
    return redirect(url_for("index"))


@app.route("/matches/import", methods=["POST"])
def import_match():
    external_match_id = request.form.get("external_match_id", "").strip()
    source_url = request.form.get("source_url", "").strip()

    if not external_match_id or not source_url:
        flash("Match ID and source URL are required", "error")
        return redirect(url_for("index"))

    if Match.query.filter_by(external_match_id=external_match_id).first():
        flash("Match already imported", "error")
        return redirect(url_for("index"))

    try:
        payload = load_json_from_source(source_url)
        parsed = parse_cricsheet_match(payload)
    except Exception as exc:
        flash(f"Failed to import match: {exc}", "error")
        return redirect(url_for("index"))

    match = Match(
        external_match_id=external_match_id,
        name=parsed["name"],
        winning_team=parsed["winning_team"],
        is_abandoned=parsed["is_abandoned"],
    )
    db.session.add(match)
    db.session.flush()

    for stat in parsed["player_stats"]:
        db.session.add(
            MatchPlayerStat(
                match_id=match.id,
                player_name=stat["player_name"],
                runs=stat["runs"],
                wickets=stat["wickets"],
            )
        )

    db.session.commit()
    flash("Match imported successfully", "success")
    return redirect(url_for("view_match", match_id=match.id))


@app.route("/matches/<int:match_id>", methods=["GET", "POST"])
def view_match(match_id: int):
    match = Match.query.get_or_404(match_id)
    users = User.query.order_by(User.name.asc()).all()
    players = sorted({stat.player_name for stat in match.player_stats})
    bowlers = sorted({stat.player_name for stat in match.player_stats if stat.wickets > 0})
    teams = []
    for ut in match.teams:
        points = ut.score.points if ut.score else None
        teams.append({"entry": ut, "points": points})

    if request.method == "POST":
        user_id = int(request.form["user_id"])
        selected_players = request.form.getlist("players")
        mvp = request.form.get("mvp", "")
        predicted_winner = request.form.get("predicted_winner", "")

        if len(selected_players) != 4:
            flash("You must select exactly 4 players", "error")
            return redirect(url_for("view_match", match_id=match_id))

        if mvp not in selected_players:
            flash("MVP must be one of selected players", "error")
            return redirect(url_for("view_match", match_id=match_id))

        has_bowler = any(player in bowlers for player in selected_players)
        if not has_bowler:
            flash("At least 1 selected player must be a bowler", "error")
            return redirect(url_for("view_match", match_id=match_id))

        if UserTeam.query.filter_by(user_id=user_id, match_id=match_id).first():
            flash("Team already submitted and locked", "error")
            return redirect(url_for("view_match", match_id=match_id))

        user_team = UserTeam(
            user_id=user_id,
            match_id=match_id,
            predicted_winner=predicted_winner,
            mvp_player_name=mvp,
            is_locked=True,
        )
        db.session.add(user_team)
        db.session.flush()

        for player in selected_players:
            db.session.add(
                TeamPick(
                    user_team_id=user_team.id,
                    player_name=player,
                    is_bowler=player in bowlers,
                    is_mvp=(player == mvp),
                )
            )

        score_value = calculate_team_score(user_team, match)
        db.session.add(TeamScore(user_team_id=user_team.id, points=score_value))
        db.session.commit()
        flash("Team submitted and locked", "success")
        return redirect(url_for("view_match", match_id=match_id))

    return render_template(
        "match.html",
        match=match,
        users=users,
        players=players,
        bowlers=bowlers,
        teams=teams,
    )


@app.route("/leaderboard")
def leaderboard():
    user_totals = []
    for user in User.query.all():
        match_rows = []
        total = 0
        for team in user.teams:
            points = team.score.points if team.score else 0
            total += points
            match_rows.append({"match": team.match.name, "points": points})
        user_totals.append({"user": user, "total": total, "matches": match_rows})

    user_totals.sort(key=lambda row: row["total"], reverse=True)
    return render_template("leaderboard.html", user_totals=user_totals)


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=5000, debug=True)
