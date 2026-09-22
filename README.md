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

[Read the Phase 1 progress notes](progress/01-Assembling-the-GUI/README.md)

### Phase 2 — Expansion

The second phase focuses on tuning the GUI for future expansion.

This includes the redesigned layout, SQLite account ownership, game artwork, image caching, settings, first-run setup, and safer Steam library refreshing.

[Read the Phase 2 progress notes](progress/02-Expansion/README.md)

## Technologies Used
-Python
-PySide6 for the desktop GUI
-Steam Web API
-SteamSpy API
-HowLongToBeat data through howlongtobeatpy
-SQLite

## Current Progress
-Steam library import with playtime data
-SteamSpy genre and tag collection
-HowLongToBeat completion time matching
-Steam achievement tracking
-Local JSON cache so collected data persists
-PySide6 desktop GUI
-Search, play-status filters, HLTB length filters, and sorting
-Random game picker based on current filters
-Incremental update buttons for HLTB, SteamSpy, and achievement data
-Project split into API, storage, UI, and update logic files

## Next Steps
-Move storage from JSON to SQLite
-Run API updates in background threads
-Combine data updates into one button
-Add game artwork and a game details view
-Add genre/tag filtering
-Add HLTB match review
-Add local machine-learning recommendations

## StreamLibraryData Documentation
Steam
-----
https://partner.steamgames.com/doc/webapi_overview
https://partner.steamgames.com/doc/webapi

Currently used for:
- Owned games
- Steam App IDs
- Game names
- Playtime
- Achievement data

SteamSpy
-----
https://steamspy.com/about

Request:
request=appdetails
appid=<Steam App ID>

Currently used for:
- Genres
- Tags

HowLongtoBeatPy
------
https://pypi.org/project/howlongtobeatpy/

Package: howlongtobeatpy

Currently used for:
- Main story time
- Main + extra time
- Completionist time
- All-styles time
- Match name
- Match similarity

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