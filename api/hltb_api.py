from howlongtobeatpy import HowLongToBeat, SearchModifiers

def get_hltb_data(game_name):
    results = HowLongToBeat().search(
        game_name,
        SearchModifiers.HIDE_DLC
    )

    if not results:
        return None

    best_match = max(results, key=lambda result: result.similarity)

    return best_match