# StreamLibraryData Summary
A desktop Steam library tool that combines Steam playtime, achievement data, SteamSpy metadata, and HowLongToBeat estimates into one local backlog browser.

Originally it was going to be a small data collection script between Steam and Howlongtobeat, but it's escalated into something that would eventually give recommendation too.

## Current Features
- Import an owned Steam library and playtime data
- Store library data locally with SQLite
- Collect genres and tags from SteamSpy
- Match games with HowLongToBeat completion estimates
- Track Steam achievement progress
- Search and filter the library through name, playtime, and HLTB length
- Pick a random game from the currently filtered library
- Bind a local database to one Steam account to avoid accidentally mixing libraries

## Project Progress

### Phase 1 — Data Collection and First GUI

The first phase focused on getting the different data sources working together and building the first usable desktop interface.

This included Steam, SteamSpy, HowLongToBeat, achievements, persistence, and filtering. 

[Read the Phase 1 progress notes](progress/01-Assembling-the-GUI/README.MD)

### Phase 2 — Expansion

The second phase focuses on tuning the GUI for future expansion.

This includes the redesigned layout, SQLite account ownership, game artwork, image caching, settings, first-run setup, and safer Steam library refreshing.

[Read the Phase 2 progress notes](progress/02-Expansion/README.MD)

### Phase 2.5 - UI Improvements - Status, Activity, and Media

The Steam library view has been expanded into more of an actual backlog manager. Games now track recent activity and last-played dates, have automatic and manual statuses, and show more information directly in the main table.

The game details panel was also expanded with activity information, genres, tags, store links, and on-demand Steam trailer playback.

This phase also included a number of UI and data fixes, particularly preserving previously collected metadata during Steam refreshes and making the interface resize properly on larger or smaller windows.

The library table was also reworked after large-library testing exposed a performance problem. The original `QTableWidget` implementation rebuilt tens of thousands of cell objects whenever the library was sorted. It was replaced with a `QTableView` backed by a custom table model, which made sorting a library of several thousand games effectively instant.

[Read the Phase 2.5 progress notes](progress/02.5-Status-Activity-and-Media/README.MD)


## Technology
- **Python**
- **PySide6 / Qt** for the desktop GUI
  - `QTableView` with a custom `QAbstractTableModel` for the game library
  - `QSplitter` and responsive layouts for the main interface
  - Qt Multimedia / `QMediaPlayer` for embedded Steam trailer playback
- **SQLite** for persistent local storage
- **requests** for Steam and SteamSpy API access
- **python-dotenv** for local API key configuration
- **howlongtobeatpy** for HowLongToBeat data
- **Steam Web API** for owned games, playtime, and achievements
- **Steam Store metadata** for artwork, store links, and trailer information

## Current Progress
- Steam library import with playtime and recent activity data
- SteamSpy, HowLongToBeat, and achievement data collection
- SQLite for collected game data
- PySide6 desktop GUI with search, filtering, sorting, and manual game statuses
- Selected-game details with artwork, activity, genres, tags, and Steam trailer playback
- Responsive layout that works with large libraries
- Qt model/view table architecture for fast sorting across several thousand games
- Incremental update tools for missing game data

## Next Steps
- Run API updates in background threads
- Combine data updates into one button
- Add genre/tag filtering
- Add HLTB match review
- Add local machine-learning recommendations

## SteamLibraryData Documentation

### Steam Web API

https://partner.steamgames.com/doc/webapi_overview  
https://partner.steamgames.com/doc/webapi

Currently used for:

- Owned games
- Steam App IDs
- Game names
- Lifetime playtime
- Recent two-week playtime
- Last-played timestamps
- Achievement data

### Steam Store Data

https://store.steampowered.com/api/appdetails

Currently used for:

- Steam trailer metadata
- HLS trailer stream URLs
- Direct MP4/WebM trailer fallbacks when available

Trailer information is requested only when the user chooses to watch a trailer.

### SteamSpy

https://steamspy.com/about

Request:

`request=appdetails`  
`appid=<Steam App ID>`

Currently used for:

- Genres
- Tags

### HowLongToBeatPy

https://pypi.org/project/howlongtobeatpy/

Package: `howlongtobeatpy`

Currently used for:

- Main story time
- Main + extra time
- Completionist time
- All-styles time
- Match name
- Match similarity

### SQLite

https://docs.python.org/3/library/sqlite3.html

Python module: `sqlite3`

Currently used for:

- Persistent game data
- Steam account association
- Steam activity data
- HLTB data
- SteamSpy genres and tags
- Achievement data
- Manual game statuses

### PySide6 / Qt

https://doc.qt.io/qtforpython-6/

Currently used for:

- Desktop GUI
- Responsive layouts and splitters
- `QTableView` and `QAbstractTableModel` for the game library
- Qt Multimedia for embedded Steam trailer playback
- Opening Steam store pages in the user's browser

## Current Focus

The next major step is moving updates away from the main GUI thread.

This should allow Steam, SteamSpy, HLTB, and achievement updates to run in the background while the rest of the application remains responsive.

After that:
- Progress indicators for data updates
- One button for updating missing game data
- Manual refresh options for older HLTB and metadata
- Better genre/tag filtering
- HLTB mismatch review
- Personalized machine-learning recommendations