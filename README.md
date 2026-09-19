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