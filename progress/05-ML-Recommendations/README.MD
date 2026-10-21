# Phase 5 - ML Recommendations

Phase 5 adds local personalized recommendations for games already present in the user's Steam library.

The current production direction is a hybrid content-based recommender with local K-Means taste clustering.

## Completed

- Audited existing library metadata for recommendation viability
- Added separate recommendation database tables
- Added optional 1-5 star enjoyment ratings
- Ratings persist between launches
- Rating changes invalidate stale recommendation results
- Added bulk recommendation data loading for confirmed Steam games
- Added sparse game-content vectors from genres and SteamSpy tags
- Added IDF weighting so uncommon tags contribute more than generic tags
- Added SteamSpy tag-strength weighting
- Added cosine similarity for game-content comparison
- Added explicit, manual, and implicit feedback modeling
- Added a learned user preference profile
- Added nearest-positive-game similarity
- Added sparse-match support adjustment
- Added a hybrid content-based baseline
- Added repeatable five-fold holdout evaluation
- Evaluated multiple ML approaches against the baseline
- Selected K-Means taste clustering after it clearly outperformed the alternatives
- Tested multiple cluster counts
- Added real-library audit tools for recommendation quality and cluster inspection
- Existing Steam, SteamSpy, HLTB, achievement, and classification systems remain unchanged

## Recommendation Data

Recommendation training uses confirmed Steam games with usable content metadata.

Current content sources include:

- Steam genres
- SteamSpy tags

Preference evidence may come from:

- explicit star ratings
- manual status
- total playtime
- playtime relative to HLTB estimates
- achievement progress

Explicit ratings are considered stronger evidence than inferred behavior.

Missing metadata is treated as missing evidence rather than negative evidence.

Unplayed games do not generate implicit preference feedback.

## Database Additions

Phase 5 adds:

- `game_ratings` - persistent 1-5 star ratings
- `recommendation_state` - metadata describing the current recommendation build
- `game_recommendations` - disposable generated recommendation results

Ratings are persistent user data.

Generated recommendation results may be rebuilt whenever relevant inputs change.

## Content Features

Games are represented as weighted sparse vectors built from genres and SteamSpy tags.

Feature weighting includes:

- smoothed inverse document frequency
- normalized SteamSpy tag strength
- square-root softening of tag weights
- L2 normalization

Cosine similarity is used to compare game-content vectors.

## Feedback Model

The feedback layer combines explicit and inferred preference evidence.

Explicit ratings map to signed preference scores.

Manual status contributes weaker preference evidence.

Implicit signals include:

- total playtime
- HLTB-relative playtime
- achievement completion

Implicit evidence is capped so unusually large playtime values cannot dominate the model.

Recent activity was evaluated but is not currently used as recommendation evidence.

## Content Baseline

The initial recommendation baseline combines two signals:

1. a global preference profile built from weighted played-game vectors
2. nearest-positive-game similarity

Sparse nearest-neighbor matches are support-adjusted so a very high cosine similarity based on only a few shared features does not dominate the ranking.

Five-fold holdout evaluation found that an even blend of the two signals performed best among the tested baseline combinations:

`0.50 * global profile similarity + 0.50 * nearest-positive similarity`

The baseline remains useful as:

- a fallback for users with insufficient clustering history
- a benchmark for evaluating ML models
- the source of nearest-positive-game similarity used by the clustered recommender

## ML Evaluation

Multiple local ML approaches were evaluated using the same five-fold holdout procedure.

The evaluation temporarily hides positively engaged games from recommendation history, treats them as candidates, and measures how highly each method recovers them.

Evaluated approaches included:

- Ridge regression
- Truncated SVD
- K-Means clustering
- One-Class SVM
- Gaussian Mixture modeling

K-Means was the only tested ML approach that clearly and consistently improved recommendation quality over the content baseline.

The other tested models were rejected after evaluation.

## K-Means Taste Clustering

K-Means is used to represent multiple distinct regions of positive user taste instead of compressing all preference history into one global centroid.

The clustered recommender combines:

- strongest learned taste-cluster similarity
- nearest-positive-game similarity

The cluster model is trained only from games with sufficiently strong positive feedback evidence.

Multiple cluster counts were evaluated. On the development dataset, five clusters produced the strongest overall result among the tested values.

The cluster audit also confirmed that learned groups were qualitatively coherent rather than arbitrary partitions.

## Current Production Direction

For users with sufficient positive recommendation history:

`content features -> positive feedback -> K-Means taste clusters -> cluster similarity + nearest-positive similarity -> ranking`

For users with insufficient history:

`content features -> global preference profile + nearest-positive similarity -> ranking`

The exact history thresholds and adaptive cluster-count rules are still being finalized.

## Testing and Evaluation

Phase 5 currently includes:

- unit tests for content features
- unit tests for feedback calculations
- unit tests for preference-profile behavior
- unit tests for baseline ranking
- unit tests for K-Means clustering
- recommendation pipeline smoke tests
- profile audits
- baseline audits
- five-fold recommendation evaluation
- cluster-count evaluation
- cluster-content inspection

Recommendation changes are evaluated against repeatable holdout metrics rather than judged only from individual example games.

## Next

- Define behavior for smaller recommendation histories
- Determine when K-Means should be enabled
- Determine how cluster count should scale with available positive evidence
- Add recommendation explanations
- Persist generated recommendation results
- Add background recommendation generation
- Add a Recommendations tab
- Add reusable genre/tag filtering
- Consider a per-game Similar Games action