from game import Game

# Games with HowLongToBeat times
def games_with_hltb_times(games: list[Game]):
    results = []

    for game in games:
        if game.preferred_hltb_time() is not None:
            results.append(game)

    return results

def sort_by_completion_time(games: list[Game]):
    return sorted(games, key=lambda game: game.preferred_hltb_time())

def games_under_hours(games: list[Game], max_hours: float):
    results = []

    for game in games:
        preferred_time = game.preferred_hltb_time()

        if preferred_time is not None and preferred_time <= max_hours:
            results.append(game)

    return results

def unplayed_games(games: list[Game]):
    results = []

    for game in games:
        if game.playtime_minutes == 0:
            results.append(game)

    return results

def started_games(games: list[Game]):
    results = []

    for game in games:
        if game.playtime_minutes > 0:
            results.append(game)

    return results

def games_with_achievements(games: list[Game]):
    result = []

    for game in games:
        if (
            game.achievements_checked
            and game.achievement_total is not None
            and game.achievement_total > 0
        ):
            result.append(game)

    return result

def sort_by_achievement_percent(games: list[Game], descending=True):
    return sorted(
        games,
        key=lambda game: game.achievement_percent() or 0,
        reverse=descending
    )