from app import Match, MatchPlayerStat, TeamPick, UserTeam, calculate_team_score


def make_team(match):
    team = UserTeam(predicted_winner="India", mvp_player_name="Virat")
    team.picks = [
        TeamPick(player_name="Virat", is_mvp=True, is_bowler=False),
        TeamPick(player_name="Bumrah", is_mvp=False, is_bowler=True),
        TeamPick(player_name="Rohit", is_mvp=False, is_bowler=False),
        TeamPick(player_name="Jadeja", is_mvp=False, is_bowler=True),
    ]
    team.match = match
    return team


def test_score_includes_mvp_and_prediction_bonus():
    match = Match(winning_team="India", is_abandoned=False)
    match.player_stats = [
        MatchPlayerStat(player_name="Virat", runs=40, wickets=0),
        MatchPlayerStat(player_name="Bumrah", runs=3, wickets=2),
        MatchPlayerStat(player_name="Rohit", runs=25, wickets=0),
        MatchPlayerStat(player_name="Jadeja", runs=10, wickets=1),
    ]

    team = make_team(match)
    # Virat MVP => (40 * 2) + Bumrah (3 + 50) + Rohit 25 + Jadeja (10+25) + winner bonus 25
    assert calculate_team_score(team, match) == 80 + 53 + 25 + 35 + 25


def test_abandoned_match_scores_zero():
    match = Match(winning_team=None, is_abandoned=True)
    match.player_stats = [MatchPlayerStat(player_name="Virat", runs=100, wickets=0)]
    team = make_team(match)
    assert calculate_team_score(team, match) == 0
