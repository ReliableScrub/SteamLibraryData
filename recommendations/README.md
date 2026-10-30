# Recommendation System

This directory contains the personalized backlog recommendation system.

The recommendation system only recommends games already present in the
user's Steam library. It does not currently discover games from the Steam
Store.

The system provides two related recommendation modes:

- **For You** uses the user's play history, ratings, statuses, HLTB data,
  achievements, genres, and SteamSpy tags to build personalized backlog
  recommendations.
- **Similar to a Game** finds unplayed backlog games that are content-similar
  to a selected owned game. This mode does not use the user's overall
  preference profile.

## High-Level Flow

### Personalized Recommendations

```text
SQLite
  |
  v
data.py
  |
  +----------------------------+
  |                            |
  v                            v
features.py                feedback.py
  |                            |
  |                +-----------+-----------+
  |                |                       |
  |                v                       v
  |            profile.py              neighbors.py
  |                |                       |
  +----------------+-----------+-----------+
                               |
                               v
                           baseline.py
                               |
                 +-------------+-------------+
                 |                           |
                 |                           v
                 |                     clustering.py
                 |                           |
                 +-------------+-------------+
                               |
                               v
                           engine.py
                               |
                  +------------+------------+
                  |                         |
                  v                         v
             diversity.py             explanations.py
                  |                         |
                  +------------+------------+
                               |
                               v
                         persistence.py
                               |
                               v
                             SQLite
                               |
                               v
                     Recommendations UI
```

### Similar to a Game

```text
Library Data
     |
     v
 features.py
     |
     v
  similar.py
     |
     v
Recommendations UI
```

## File Responsibilities

File | Responsibility
--- | ---
`data.py` | Loads recommendation-relevant game data from SQLite into `RecommendationGameData` objects.
`features.py` | Converts Steam genres and SteamSpy tags into normalized weighted content vectors used by the recommendation and similarity systems.
`feedback.py` | Converts ratings, manual status, playtime, HLTB data, and achievements into preference evidence with a score and confidence.
`profile.py` | Combines feedback from played games into the user's aggregate preference profile.
`neighbors.py` | Finds positively received played games that are most content-similar to each candidate. Similarity is adjusted for shared-feature support and weighted by the strength of the user's positive feedback. Production scoring uses the three strongest neighbors.
`baseline.py` | Scores unplayed candidates using a 50/50 blend of aggregate preference-profile similarity and K=3 feedback-weighted positive-neighborhood similarity. This is also the fallback recommender when there is not enough positive history for clustering.
`clustering.py` | Learns multiple positive taste profiles using feedback-weighted K-Means. The number of clusters adapts to the amount of usable positive history. When clustering is available, candidates are scored using a 50/50 blend of closest-cluster similarity and positive-neighborhood similarity.
`engine.py` | Orchestrates personalized recommendation generation. It builds features and the preference profile, calculates neighborhood scores, chooses K-Means or baseline mode, produces the authoritative ranking, builds explanations, and generates diversified Top Picks.
`diversity.py` | Applies MMR diversification to the small Top Picks set so that the visible recommendations are less repetitive. It does not change the authoritative full recommendation ranking.
`explanations.py` | Converts the model's actual taste traits and supporting played-game similarities into human-readable recommendation explanations. Explanations never change recommendation scores.
`persistence.py` | Saves and loads recommendation state, recommendation scores, Top Pick status, explanation data, and build metadata in SQLite.
`similar.py` | Powers the separate Similar to a Game mode. It compares owned games using content similarity and shared genres/tags, applies sparse-match support adjustment, and returns similar unplayed backlog games without using the user's global preference profile.

## Personalized Scoring

The personalized recommendation system uses two scoring modes.

### Baseline Mode

Baseline mode is used when there is not enough suitable positive history to
train taste clusters.

Each unplayed candidate receives:

```text
50% preference-profile similarity
50% K=3 feedback-weighted positive-neighborhood similarity
```

The preference profile represents the user's overall learned taste.

The neighborhood component looks at the three strongest positively received
played games that resemble the candidate. Their contribution is weighted by
the strength and confidence of the feedback associated with those games.

This gives the model both:

- a broad view of the user's overall preferences
- specific examples of played games that resemble the candidate

### K-Means Mode

When enough suitable positive played history is available, the system learns
multiple taste clusters with K-Means.

The number of clusters adapts to the amount of usable positive training
history rather than always using a fixed cluster count.

Each unplayed candidate is matched against its closest learned taste cluster
and receives:

```text
50% closest taste-cluster similarity
50% K=3 feedback-weighted positive-neighborhood similarity
```

The neighborhood component remains part of the score so that clustering does
not replace the specific played-game evidence.

If a usable cluster model cannot be trained, the engine automatically falls
back to baseline mode.

## Positive Neighborhoods

`neighbors.py` provides the specific-history component used by both
personalized scoring modes.

Only played games with positive usable feedback can become positive
references.

For each candidate:

1. Content similarity is calculated against positive played references.
2. Similarity is reduced when the match is supported by very few shared
   features.
3. References are ranked by support-adjusted similarity.
4. The three strongest references are retained.
5. Their similarities are combined using feedback strength and confidence.

This avoids allowing a single superficially similar game or a sparse
one-feature match to dominate the recommendation score.

The supporting games shown in recommendation explanations come from this same
neighborhood data.

## Taste Clustering

`clustering.py` uses feedback-weighted K-Means to model multiple areas of the
user's taste.

Only played games with sufficiently positive feedback and usable content
vectors participate in cluster training.

Positive games with stronger preference evidence have greater influence on
the learned cluster centers.

The cluster count currently adapts to the amount of positive history:

```text
Fewer than 15 usable positive games -> no clustering
15-19                             -> 2 clusters
20-29                             -> 3 clusters
30-49                             -> 4 clusters
50+                               -> 5 clusters
```

Each recommendation candidate is compared against all learned cluster
centers and uses the similarity to its closest cluster as the clustering
portion of its score.

## Top Picks and Diversity

The full recommendation list is always kept in authoritative recommendation
score order.

A small Top Picks set is separately reranked using Maximal Marginal Relevance
(MMR).

MMR balances:

- the original recommendation score
- similarity to recommendations already selected as Top Picks

This reduces cases where the visible Top Picks are dominated by several
nearly identical games.

Diversification does not rewrite the full recommendation ranking or change
the underlying recommendation scores.

## Explanations

Recommendation explanations are generated from information already used by
the model.

They can include:

- important matching taste traits
- whether the recommendation was based on the global profile or a learned
  taste cluster
- similar positively received games the user has already played
- shared traits with those supporting games
- the strength of the supporting similarity and preference evidence

Genre and tag entries representing the same human-readable trait are merged
for explanation purposes where appropriate.

Generic or unhelpful traits may be suppressed from displayed explanations.

Explanation generation is read-only with respect to ranking. It does not
alter recommendation scores.

## Similar to a Game

`similar.py` powers the separate Similar to a Game feature.

This feature answers a different question from For You:

```text
"What unplayed games in my library are similar to this particular game?"
```

It does not use:

- the global preference profile
- ratings as recommendation preference
- K-Means taste clusters

Instead, it compares the selected reference game's content vector against
other owned games.

By default, results are limited to unplayed candidates.

Similarity is based on the same genre/tag content representation used by the
personalized recommendation system.

Sparse matches are support-adjusted so that a perfect cosine match based on
only one or two shared features is not treated as strongly as a match backed
by a broader set of shared traits.

The UI may then apply the normal recommendation filters to the similarity
results.

## Persistence

Generated personalized recommendation builds are stored in SQLite.

Persisted data includes:

- recommendation method
- model and feature versions
- build timestamp
- training and candidate counts
- recommendation scores
- Top Pick status
- serialized explanation data

The Recommendations UI can therefore display the latest generated results
without rebuilding the model every time the tab is opened.

Recommendation-relevant library changes mark the current recommendation
state as needing a rebuild.

Multiple changes made during the same session are coalesced rather than
forcing a complete rebuild after every individual edit.

Recommendation builds are also deferred while Maintenance is actively
updating library data.

## Design Goals

The recommendation system is intentionally:

- **Local** - recommendation modeling runs against the user's local library
  data.
- **Backlog-focused** - it recommends games the user already owns rather than
  attempting Steam Store discovery.
- **Explainable** - visible recommendations can be traced back to learned
  tastes and similar played games.
- **Deterministic** - fixed model settings are used where practical so
  recommendation results can be reproduced and audited.
- **Lightweight** - the system is designed to run comfortably as part of the
  desktop application without requiring an external recommendation service.
- **Fallback-safe** - users with limited history can still receive
  recommendations without requiring a trained clustering model.