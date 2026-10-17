# Phase 5 — ML Recommendations

Phase 5 adds local personalized recommendations for games already in the user's Steam library.

## Completed

- Audited existing library data for recommendation viability
- Added separate recommendation database tables
- Added optional 1–5 star enjoyment ratings
- Ratings persist between launches
- Rating changes invalidate stale recommendation results
- Existing Steam, SteamSpy, HLTB, achievement, and classification systems remain unchanged

## Recommendation Data

The current library provides enough data to support recommendation work:

- confirmed games
- played confirmed games
- unplayed confirmed games
- unplayed games with tag or genre data
- 66,117 tag assignments
- 9,388 genre assignments

Explicit ratings are used because playtime alone does not reliably indicate whether a game was liked.

## Database Additions

Phase 5 adds:

- `game_ratings` — permanent 1–5 star ratings
- `recommendation_state` — information about the current recommendation build
- `game_recommendations` — disposable generated recommendation results

## Next

- Build the recommendation training dataset
- Create a content-based baseline
- Train and evaluate a local ML model
- Generate recommendation explanations
- Add a Recommendations tab