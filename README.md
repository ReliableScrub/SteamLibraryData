# SteamLibraryData

SteamLibraryData is a desktop Steam library and backlog manager that combines Steam playtime and achievement data with SteamSpy metadata and HowLongToBeat estimates.

The project started as a small data-collection tool for combining Steam and HowLongToBeat information, but has gradually expanded into a full local backlog browser with filtering, activity tracking, data management, and future recommendation features.

## Current Features

- Import an owned Steam library with playtime and recent activity data
- Store collected data locally with SQLite
- Collect genres and tags from SteamSpy
- Match games with HowLongToBeat completion estimates
- Review ambiguous HowLongToBeat matches before accepting them
- Track Steam achievement progress
- Classify Steam library entries such as games, DLC, and software
- Search, filter, and sort the library
- Track automatic and manual backlog statuses
- View selected-game details, artwork, metadata, and Steam trailers
- Pick a random game from the currently filtered library
- Update missing external data in the background without blocking the interface
- Cancel long-running update operations
- Bind the local database to one Steam account to prevent accidental library mixing
- Manage SteamID64 and Steam Web API credentials from the Settings tab

## Steam Web API Setup

SteamLibraryData uses the official Steam Web API to import owned games and retrieve account-specific Steam data.

The application does **not** include or distribute a Steam Web API key. Each user must provide their own.

### Requirements

You will need:

- your SteamID64
- your personal Steam Web API key
- appropriate Steam profile and library visibility for the data you want to retrieve

A standard Steam Web API key can be registered at:

https://steamcommunity.com/dev/apikey

SteamLibraryData does not require your Steam password, Steam Guard information, or a Steamworks publisher key.

### Configuration

On first launch, SteamLibraryData asks for your Steam Web API key.

The key is stored using the operating system's credential manager rather than in the SQLite database or `settings.json`.

Your SteamID64 and Steam Web API key can later be changed from the **Settings** tab.

Changing to a different Steam account requires resetting the account-specific local database so data from multiple Steam accounts is not mixed.

Treat your Steam Web API key as a private credential. Do not post it publicly or include it in screenshots, bug reports, or repository files.

## Local Data

SteamLibraryData stores user data outside the project directory in the operating system's application-data location.

- **Windows:** `%APPDATA%\SteamLibraryData`
- **macOS:** `~/Library/Application Support/SteamLibraryData`
- **Linux:** `$XDG_DATA_HOME/SteamLibraryData` or `~/.local/share/SteamLibraryData`

This includes the local SQLite database, normal application settings, and cached game artwork.

The Steam Web API key is stored separately through the operating system credential manager.

## Project Progress

### Phase 1 - Data Collection and First GUI

The first phase established the core application: Steam library importing, SteamSpy metadata, HowLongToBeat estimates, achievements, local persistence, filtering, and the first usable GUI.

[Read the Phase 1 progress notes](progress/01-Assembling-the-GUI/README.MD)

### Phase 2 - Expansion

Phase 2 expanded the application structure and prepared the GUI for a larger feature set.

This included the redesigned layout, SQLite account ownership, game artwork, image caching, settings, first-run setup, and safer Steam library refreshing.

[Read the Phase 2 progress notes](progress/02-Expansion/README.MD)

### Phase 2.5 - Status, Activity, and Media

Phase 2.5 moved SteamLibraryData closer to a full backlog manager.

Games gained recent activity, last-played dates, automatic and manual statuses, richer selected-game details, store links, and on-demand Steam trailer playback.

The library table was also migrated from `QTableWidget` to a `QTableView` backed by a custom model after large-library testing exposed significant sorting-performance problems.

[Read the Phase 2.5 progress notes](progress/02.5-Status-Activity-and-Media/README.MD)

### Phase 3 - External Data Infrastructure

Phase 3 focused on making external-data updates reliable enough for large Steam libraries.

Steam, SteamSpy, HowLongToBeat, and achievement updates were moved into background workers with progress reporting, cancellation, safer persistence, and better failure handling.

HowLongToBeat matching was expanded with conservative automatic matching, manual review for ambiguous results, Steam App ID verification, caching, and a persistent search client.

This phase also added Steam app classification and reorganized the GUI into separate library, update, settings, controller, and table-model components.

[Read the Phase 3 progress notes](progress/03-External-Data-Infrastructure/README.MD)

### Phase 4 - User Configuration and Application Hardening

Phase 4 focuses on preparing SteamLibraryData to behave like a normal standalone desktop application rather than a development-only project.

Work completed so far includes:

- moving database, settings, and cached images into OS application-data directories
- replacing `.env` configuration with in-app settings
- securely storing the Steam Web API key through the OS credential manager
- adding first-run API key setup and validation
- adding SteamID64 and API-key management to the Settings tab
- adding official repository, feedback, and bug-report links
- improving Steam, SteamSpy, and HowLongToBeat network failure handling
- preserving existing local data when external-service updates fail

The remaining Phase 4 work is primarily documentation and final regression testing.

[Read the Phase 4 progress notes](progress/04-User-Config/README.MD)


### Phase 5 - ML Recommendations

Phase 5 added local personalized recommendations for games already present in the user's Steam library.

The recommendation system uses a hybrid content-based approach built from Steam genres, SteamSpy tags, local user feedback, positive-neighbor similarity, and K-Means taste clustering.

For users without enough suitable positive history for clustering, the application automatically falls back to a simpler content-based preference model.

Major work included:

- persistent 1-5 star enjoyment ratings
- weighted content vectors from Steam genres and SteamSpy tags
- IDF and SteamSpy tag-strength weighting
- explicit, manual, and implicit preference feedback
- a learned global preference profile
- feedback-weighted positive-neighbor matching
- sparse-match support adjustment
- adaptive local K-Means taste clustering
- persisted recommendation builds and explanation data
- personalized **For You** recommendations
- recommendation diversification to reduce repetitive results
- **Similar to a Game** content-similarity search
- reusable recommendation filtering by type, genre, tag, and HLTB data
- recommendation explanations showing taste traits and supporting played games
- Steam artwork, Store access, HLTB information, and embedded trailers
- responsive, scrollable recommendation detail layouts
- automated tests and real-library recommendation audits

Several local ML approaches were evaluated during development, including Ridge regression, Truncated SVD, K-Means clustering, One-Class SVM, and Gaussian Mixture modeling.

K-Means was retained because it produced the clearest improvement over the simpler content baseline while remaining local, deterministic, relatively lightweight, and explainable.

Recommendation behavior is evaluated with repeatable holdout testing rather than relying only on individual recommendation examples.

[Read the Phase 5 progress notes](progress/05-ML-Recommendations/README.MD)


## Technology

- **Python**
- **PySide6 / Qt** for the desktop GUI
  - `QTableView` and `QAbstractTableModel` for the game library
  - responsive Qt layouts and splitters
  - Qt Multimedia for Steam trailer playback
- **SQLite** for persistent local storage
- **requests** for HTTP API access
- **keyring** for secure Steam Web API credential storage
- **howlongtobeatpy** for HowLongToBeat data
- **Steam Web API** for owned games, playtime, achievements, and Steam application data
- **SteamSpy** for genres and tags
- **Steam Store data** for artwork, store links, and trailer information

## Data Sources

### Steam Web API

SteamLibraryData currently uses the Steam Web API for:

- owned games
- Steam App IDs
- game names
- lifetime playtime
- recent two-week playtime
- last-played timestamps
- achievement data
- Steam application classification

Documentation:

https://partner.steamgames.com/doc/webapi_overview

https://partner.steamgames.com/doc/webapi

### Steam Store

Steam Store data is used for:

- game artwork
- store links
- trailer metadata and playback

Trailer information is requested only when needed.

### SteamSpy

SteamSpy is used for:

- genres
- tags

https://steamspy.com/about

### HowLongToBeat

HowLongToBeat data is used for:

- main story time
- main + extra time
- completionist time
- all-styles time
- match information
- manual review of uncertain matches

SteamLibraryData uses the `howlongtobeatpy` package as part of its HLTB integration.

https://pypi.org/project/howlongtobeatpy/

## Local Storage

SQLite is used for persistent application data, including:

- Steam library information
- Steam account association
- playtime and activity data
- Steam classification
- HowLongToBeat data
- SteamSpy genres and tags
- achievement progress
- manual game statuses

Game artwork is cached separately on disk.

## Current Focus

The current focus is completing **Phase 4 - User Configuration and Application Hardening**.

Remaining work:

- finalize user-facing setup documentation
- run a final regression and cleanup pass
- remove obsolete dependencies and dead code

After Phase 4, **Phase 5** will focus on distribution:

- Windows executable packaging
- macOS packaging
- clean-machine installation testing
- packaging-specific fixes
- code signing and notarization considerations

## Future Ideas

Potential future work includes:

- improved genre and tag filtering
- per-game refresh controls for external metadata
- saved and external guide links
- additional backlog-management tools
- personalized local game recommendations
- further packaging and distribution improvements