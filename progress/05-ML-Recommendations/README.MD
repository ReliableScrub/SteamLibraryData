# Phase 5 - ML Recommendations

Phase 5 adds local personalized recommendations for games already present in the user's Steam library.

The production recommender is a hybrid content-based system built from Steam genres, SteamSpy tags, user feedback, and local K-Means taste clustering. For smaller recommendation histories, it automatically falls back to a simpler content-based model.

## Completed

- Added persistent 1-5 star enjoyment ratings
- Added recommendation-specific database tables and bulk data loading
- Added weighted sparse content vectors from Steam genres and SteamSpy tags
- Added IDF weighting, SteamSpy tag-strength weighting, and cosine similarity
- Added explicit, manual, and implicit feedback modeling
- Added a learned user preference profile
- Added feedback-weighted positive-neighborhood matching
- Added sparse-match support adjustment
- Added an adaptive K-Means taste-clustering model
- Added a content-based fallback for smaller recommendation histories
- Evaluated multiple local ML approaches and clustering configurations
- Added repeatable holdout evaluation for recommendation quality
- Added persisted recommendation builds and explanations
- Added a dedicated Recommendations tab
- Added personalized **For You** recommendations
- Added **Similar to a Game** content-similarity search
- Added type, genre, tag, and HLTB filtering
- Added recommendation diversification to avoid overly repetitive result sets
- Added Steam artwork, Store access, HLTB data, and embedded trailers
- Added responsive, scrollable recommendation detail panels
- Added recommendation and Phase 5 regression audits
- Consolidated recommendation tests and diagnostic tools

Existing Steam, SteamSpy, HLTB, achievement, and classification systems remain separate from the recommendation model and provide data to it where appropriate.

## Recommendation Data

Recommendation training uses confirmed Steam games with usable content metadata.

Content features currently come from:

- Steam genres
- SteamSpy tags

Preference evidence may come from:

- explicit 1-5 star ratings
- manual game status
- total playtime
- playtime relative to HLTB estimates
- achievement progress

Explicit ratings are treated as stronger evidence than inferred behavior.

Missing metadata is treated as missing evidence rather than negative evidence, and unplayed games do not generate implicit preference feedback.

## Database Additions

Phase 5 adds:

- `game_ratings` - persistent 1-5 star user ratings
- `recommendation_state` - metadata describing the current recommendation build
- `game_recommendations` - generated scores, match tiers, and explanation data

Ratings are persistent user data.

Generated recommendations are derived data and can be rebuilt whenever relevant library data or ratings change.

## Recommendation Model

Games are represented as sparse weighted feature vectors.

Feature processing includes:

- Steam genre features
- SteamSpy tag features
- smoothed inverse document frequency
- normalized SteamSpy tag strength
- square-root softening of tag weights
- L2 normalization

Cosine similarity is used to compare game-content vectors.

The recommender also builds a feedback-weighted positive neighborhood from games the user has played and shown positive evidence toward. Sparse matches are support-adjusted so that a near-perfect match on only one or two weakly shared features does not dominate a stronger multi-feature match.

### Smaller histories

When there is not enough suitable positive history for clustering, recommendations use:

```text
global preference profile
+ feedback-weighted positive neighborhood
-> recommendation ranking
```

### Larger histories

With enough positive history, the recommender trains local K-Means taste clusters:

```text
content features
-> positive feedback
-> K-Means taste clusters
-> cluster similarity + positive-neighborhood similarity
-> recommendation ranking
```

The number of clusters is selected adaptively from the amount of usable positive history, up to five clusters.

This allows the model to represent multiple areas of taste instead of forcing all preferences into one global profile.

## ML Evaluation

Recommendation changes are evaluated using repeatable holdout testing against the user's real library data.

Approaches evaluated during Phase 5 included:

- content-based preference profiles
- nearest-positive and multi-neighbor similarity
- Ridge regression
- Truncated SVD
- K-Means clustering
- One-Class SVM
- Gaussian Mixture modeling
- multiple K-Means cluster counts
- multiple positive-neighborhood sizes

K-Means was retained because it produced the clearest improvement over the simpler content baseline while remaining deterministic, local, explainable, and relatively lightweight.

Experimental approaches that did not improve results were removed rather than retained only for additional model complexity.

## Recommendations UI

The Recommendations tab provides two modes.

### For You

Displays up to ten personalized games selected from the saved recommendation build.

The view includes:

- recommendation match strength
- major taste traits
- supporting games previously played
- shared traits
- HLTB estimates
- Steam type
- Steam artwork
- Steam Store access
- embedded trailers
- type, genre, tag, and HLTB filters

Filters narrow the saved recommendation pool without rebuilding or retraining the recommendation model.

A diversification pass is applied when selecting the displayed shortlist so that closely related games do not unnecessarily dominate the entire page.

The media/detail area is vertically scrollable so artwork, HLTB information, trailers, navigation, and Store controls remain usable at smaller window heights.

### Similar to a Game

Allows an owned game to be selected as a reference and ranks unplayed backlog games by content similarity.

The view includes:

- similarity strength
- shared traits
- HLTB information
- artwork
- Steam Store access
- embedded trailers
- the same reusable recommendation filters

This mode uses genre/tag content similarity rather than the user's personalized recommendation profile.

## Testing

The test suite is organized around behavior rather than individual implementation constants.

Current coverage includes:

- database and rating persistence
- Steam API parsing
- content-vector construction
- feedback calculations
- preference-profile behavior
- positive-neighborhood matching
- Similar to a Game ranking
- baseline recommendation behavior
- K-Means clustering
- diversification
- recommendation explanations
- recommendation-engine integration
- Maintenance and Recommendations UI regression checks

Run the complete automated test suite with:

```powershell
pytest
```

For verbose output:

```powershell
pytest -v
```

## Audits and Evaluation

Phase 5 also includes real-library diagnostics that complement the isolated pytest suite.

### Database and Phase 5 health

```powershell
python -m tools.phase5_audit
```

Checks database integrity, classifications, update coverage, HLTB state, achievements, metadata mappings, ratings, and saved recommendation state.

### Production recommendation audit

```powershell
python -m tools.recommendation_audit
```

Builds recommendations in memory and checks ranking integrity, explanations, supporting-game references, top picks, and other production invariants.

An optional diversification preview can also be requested:

```powershell
python -m tools.recommendation_audit --diversity-weight 0.85
```

### Recommendation evaluation

History-size evaluation:

```powershell
python -m tools.recommendation_evaluation history
```

Positive-neighborhood evaluation:

```powershell
python -m tools.recommendation_evaluation neighbors
```

Cluster-count evaluation:

```powershell
python -m tools.recommendation_evaluation clusters
```

Additional options are available through:

```powershell
python -m tools.recommendation_evaluation --help
```

or, for example:

```powershell
python -m tools.recommendation_evaluation history --help
```

### Recommendation inspection

General recommendation-data summary:

```powershell
python -m tools.recommendation_inspect summary
```

Inspect learned taste clusters:

```powershell
python -m tools.recommendation_inspect clusters
```

Inspect a specific game's feature representation and similar games:

```powershell
python -m tools.recommendation_inspect game "Game Name"
```

Inspect SteamSpy tag coverage:

```powershell
python -m tools.recommendation_inspect tags
```

Inspect a specific tag:

```powershell
python -m tools.recommendation_inspect tag "Mystery Dungeon"
```

### Persistence audit

```powershell
python -m tools.recommendation_persistence_audit
```

Unlike the other audits, this command intentionally generates and saves a fresh recommendation build before validating the persisted state.

## Phase 5 Status

Phase 5 is functionally complete.

The recommendation model, persistence layer, filtering, explanations, Similar to a Game search, embedded media, responsive recommendation layout, tests, and real-library audit tools are all implemented.

Further recommendation changes should primarily be driven by observed recommendation quality, regressions, or clearly useful UX improvements rather than additional model complexity for its own sake.