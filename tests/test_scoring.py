from datetime import datetime, timedelta

from app import Match, MatchPlayerStat, TeamPick, UserTeam, calculate_team_score


def test_score_includes_mvp_and_prediction_bonus():
    match = Match(
        external_match_id="1",
        name="A vs B",
        team_a="India",
        team_b="Australia",
        starts_at=datetime.utcnow() + timedelta(hours=1),
        winning_team="India",
        is_abandoned=False,
    )
    match.player_stats = [
        MatchPlayerStat(player_name="Virat", runs=40, wickets=0),
        MatchPlayerStat(player_name="Bumrah", runs=3, wickets=2),
        MatchPlayerStat(player_name="Rohit", runs=25, wickets=0),
        MatchPlayerStat(player_name="Jadeja", runs=10, wickets=1),
    ]

    team = UserTeam(predicted_winner="India", mvp_player_name="Virat")
    team.picks = [
        TeamPick(player_name="Virat", is_mvp=True, is_bowler=False),
        TeamPick(player_name="Bumrah", is_mvp=False, is_bowler=True),
        TeamPick(player_name="Rohit", is_mvp=False, is_bowler=False),
        TeamPick(player_name="Jadeja", is_mvp=False, is_bowler=True),
    ]

    assert calculate_team_score(team, match) == 218


def test_abandoned_match_scores_zero():
    match = Match(
        external_match_id="2",
        name="A vs B",
        team_a="India",
        team_b="Australia",
        starts_at=datetime.utcnow(),
        winning_team=None,
        is_abandoned=True,
    )
    match.player_stats = [MatchPlayerStat(player_name="Virat", runs=99, wickets=0)]
    team = UserTeam(predicted_winner="India", mvp_player_name="Virat")
    team.picks = [TeamPick(player_name="Virat", is_mvp=True, is_bowler=False)]
    assert calculate_team_score(team, match) == 0
