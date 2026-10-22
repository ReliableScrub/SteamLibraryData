# Recommendation System

This directory contains the personalized backlog recommendation system.

The recommendation system only recommends games already present in the
user's Steam library. It does not currently discover games from the Steam
Store.

## High-Level Flow

```text
SQLite
  |
  v
data.py
  |
  +------------------------+
  |                        |
  v                        v
features.py             feedback.py
  |                        |
  |                        v
  |                     profile.py
  |                        |
  +------------+-----------+
               |
               v
           baseline.py
               |
               +----------------------+
               |                      |
               |                      v
               |                 clustering.py
               |                      |
               +-----------+----------+
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

File    -     Responsibility
--------------------------------------------------------------------------------------------------------
`data.py` - Loads recommendation-relevant game data from SQLite into `RecommendationGameData` objects.
`features.py` - Converts genres and SteamSpy tags into normalized weighted content vectors used for similarity calculations.
`feedback.py` - Converts ratings, manual status, playtime, HLTB data, and achievements into preference evidence.
`profile.py` - Combines feedback from played games into the user's overall preference profile.
`baseline.py` - Scores candidates using the preference profile and the most similar positively received played game. Also provides the fallback recommender when there is not enough history for clustering.
`clustering.py` - Learns multiple taste clusters with K-Means and scores candidates against the closest taste cluster.
`engine.py` - Organizer. Builds the recommendation model, chooses K-Means or fallback mode, ranks candidates, and produces Top Picks.
`diversity.py` - Applies MMR diversification to a small Top Picks set without changing the authoritative full ranking.
`explanations.py` - Converts the model's actual similarity contributions into human-readable recommendations. Explanations never change the recommendation scores.
`persistence.py` - Saves and loads generated recommendation state and recommendation rows in SQLite.