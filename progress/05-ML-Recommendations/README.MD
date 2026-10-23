# Phase 5 - ML Recommendations

Phase 5 adds local personalized recommendations for games already present in the user's Steam library.

The production model is a hybrid content-based recommender using local K-Means taste clustering, with a simpler content-based fallback when there is not enough positive history for clustering.

## Completed

- Added persistent 1-5 star enjoyment ratings
- Added recommendation-specific database tables
- Added bulk recommendation data loading
- Added sparse content vectors from Steam genres and SteamSpy tags
- Added IDF and SteamSpy tag-strength weighting
- Added cosine similarity for game comparison
- Added explicit, manual, and implicit feedback modeling
- Added a learned user preference profile
- Added nearest-positive-game similarity
- Added sparse-match support adjustment
- Added a hybrid content-based baseline
- Added repeatable five-fold holdout evaluation
- Evaluated several local ML approaches
- Selected K-Means after it clearly outperformed the tested alternatives
- Evaluated multiple K-Means cluster counts
- Selected five clusters for the current development library
- Added real-library recommendation and cluster audits
- Added persistent generated recommendation results
- Added recommendation explanations
- Added a dedicated Recommendations tab
- Added personalized **For You** recommendations
- Added reusable type, genre, tag, and HLTB filtering
- Added **Similar to a Game** content-similarity search
- Added Steam artwork, Store links, HLTB data, and embedded trailers to recommendation details

Existing Steam, SteamSpy, HLTB, achievement, and classification systems remain separate from the recommendation model.

## Recommendation Data

Recommendation training uses confirmed Steam games with usable content metadata.

Content features currently come from:

- Steam genres
- SteamSpy tags

Preference evidence may come from:

- explicit star ratings
- manual status
- total playtime
- playtime relative to HLTB estimates
- achievement progress

Explicit ratings are treated as stronger evidence than inferred behavior.

Missing metadata is treated as missing evidence rather than negative evidence.

Unplayed games do not generate implicit preference feedback.

## Database Additions

Phase 5 adds:

- `game_ratings` - persistent 1-5 star ratings
- `recommendation_state` - information about the current recommendation build
- `game_recommendations` - generated recommendation results and explanations

Ratings are persistent user data.

Generated recommendations are derived data and can be rebuilt whenever relevant inputs change.

## Recommendation Model

Games are represented as weighted sparse vectors built from genres and SteamSpy tags.

Feature weighting includes:

- smoothed inverse document frequency
- normalized SteamSpy tag strength
- square-root softening of tag weights
- L2 normalization

Cosine similarity is used for game-content comparison.

The original content baseline combines:

`0.50 * global preference similarity + 0.50 * nearest-positive similarity`

This remains useful as both a benchmark and a fallback.

For users with enough positive recommendation history, the production recommender instead uses K-Means to represent multiple areas of positive taste:

`content features -> positive feedback -> K-Means taste clusters -> cluster similarity + nearest-positive similarity -> ranking`

For users without enough suitable history:

`content features -> global preference profile + nearest-positive similarity -> ranking`

Five clusters currently perform best on the development library.

## ML Evaluation

The recommendation system was evaluated using repeatable five-fold holdout testing.

Tested approaches included:

- Ridge regression
- Truncated SVD
- K-Means clustering
- One-Class SVM
- Gaussian Mixture modeling

K-Means was the only tested ML approach that clearly and consistently improved recommendation quality over the content baseline.

The other approaches were rejected rather than retained simply for additional model complexity.

## Recommendations UI

The Recommendations tab currently provides two modes.

### For You

Displays up to ten personalized recommendations from the saved recommendation build.

The view includes:

- recommendation match strength
- explanation of major taste traits
- supporting games previously played
- shared traits
- HLTB estimates
- Steam type
- artwork
- Steam Store access
- embedded trailers
- type, genre, tag, and HLTB filters

Filters narrow the existing recommendation pool without retraining the model.

A small diversification step is used when choosing the displayed recommendations so the list is not dominated by nearly identical games.

### Similar to a Game

Allows an owned game to be selected as a reference and ranks unplayed backlog games by content similarity.

The view includes:

- similarity strength
- shared traits
- HLTB data
- artwork
- Store access
- embedded trailers

This mode uses genre/tag content similarity rather than the user's full personalized taste profile.

## Testing

Phase 5 includes:

- unit tests for content features
- unit tests for feedback calculations
- unit tests for preference-profile behavior
- unit tests for baseline ranking
- unit tests for K-Means clustering
- recommendation pipeline smoke tests
- profile and baseline audits
- five-fold recommendation evaluation
- cluster-count evaluation
- cluster-content inspection
- real-library recommendation audits

Recommendation changes are evaluated with repeatable holdout metrics rather than judged only from individual examples.

## Remaining things to do

The recommendation model itself is largely complete.

Remaining Phase 5 work is mainly UI and edge-case polish:

- better empty states when there are no recommendations
- clearer handling when filters remove every result
- better handling when Similar to a Game lacks usable metadata
- responsive layout improvements for large window sizes
- permanent trailer-preview space so the layout does not shift when playback starts
- final recommendation UI cleanup