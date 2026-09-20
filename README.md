# StreamLibraryData Summary
Steam Library Data Collector to merge with Howlongtobeat times

# StreamLibraryData Documentation
Steam
-----
https://partner.steamgames.com/doc/webapi_overview
https://partner.steamgames.com/doc/webapi

GetOwnedGames:
Fields used:
- appid
- name
- playtime_forever

SteamSpy
-----
https://steamspy.com/about

Request:
request=appdetails
appid=<Steam App ID>

Fields used:
- genre
- tags

HowLongtoBeatPy
------
https://pypi.org/project/howlongtobeatpy/

Package: howlongtobeatpy

Methods:
- search()
- async_search()

Fields used:
- game_name
- similarity
- main_story
- main_extra
- completionist
- all_styles

Useful:
SearchModifiers.HIDE_DLC
Default similarity filtering: > 0.4

# Technologies Used
Python
PySide6 for the desktop GUI
Steam Web API
SteamSpy API
HowLongToBeat data through howlongtobeatpy
JSON for current local persistence
python-dotenv for API key configuration

# Current Progress
Steam library import with playtime data
SteamSpy genre and tag collection
HowLongToBeat completion time matching
Steam achievement tracking
Local JSON cache so collected data persists
PySide6 desktop GUI
Search, play-status filters, HLTB length filters, and sorting
Random game picker based on current filters
Incremental update buttons for HLTB, SteamSpy, and achievement data
Project split into API, storage, UI, and update logic files

# Next Steps
Move storage from JSON to SQLite
Run API updates in background threads
Combine data updates into one button
Add game artwork and a game details view
Add genre/tag filtering
Add HLTB match review
Add local machine-learning recommendations