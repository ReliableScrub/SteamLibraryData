# Phase 5 - ML Recommendations

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

- `game_ratings` - permanent 1–5 star ratings
- `recommendation_state` - information about the current recommendation build
- `game_recommendations` - disposable generated recommendation results

## Recommendation Pipeline Progress

- Added recommendation data loader for confirmed Steam games
- Added sparse content feature vectors using genres and SteamSpy tags
- Added IDF weighting so uncommon tags contribute more than generic tags
- Added cosine similarity for comparing game content
- Audited similarity results against the real library
- Added explicit feedback from 1–5 star ratings
- Added manual-status feedback for Completed and Dropped games
- Added implicit engagement signals from:
  - total playtime
  - playtime relative to HLTB estimates
  - achievement progress
- Missing HLTB or achievement data is treated as missing evidence, not negative evidence
- Unplayed games do not produce implicit feedback
- Implicit feedback is deliberately capped so extreme playtime does not dominate the preference model
- Recent activity was audited but is not currently used as recommendation evidence
- Added automated tests and real-library audit tools for recommendation features and feedback

## Current Recommendation Design

The recommender is currently a single-user content-based system with hybrid explicit and implicit feedback.

Content features describe what a game is:

- genres
- SteamSpy tags

Feedback describes how strongly the user appears to have liked or engaged with a played game:

- explicit star ratings
- manual Completed / Dropped status
- playtime
- HLTB-relative playtime
- achievement progress

Explicit ratings are treated as stronger evidence than inferred behavior.

## Next

- Combine explicit, manual, and implicit feedback into one final per-game feedback signal
- Build the user's preference profile from positively and negatively weighted game features
- Rank unplayed games against the preference profile
- Build and evaluate the content-based recommendation baseline
- Add recommendation explanations
- Evaluate a simple local ML model against the baseline
- Add a Recommendations tab