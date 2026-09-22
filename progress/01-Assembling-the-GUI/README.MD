# Phase 1 — Data Collection and First GUI

So my steam library is massive. The original goal was much smaller: read my Steam library, attach HowLongToBeat estimates to the games, and eventually use that information to help decide what to play.

<img src="Before-GUI-Change.png" alt="Before the GUI Change" width="50%">

## Steam Library Import

The first working version used the Steam Web API to retrieve the owned game library.

The main fields I needed were:
- App ID
- Game name
- Total Steam playtime
- Achievements (this was added later)
- Artwork (Last add step)

It was simple enough to the access to the Steam API.

## HowLongToBeat Matching

Then it was as 'easy' as getting HowLongToBeat's data. Someone made a Python API to read data from the website, so getting access to that information was easy.

For a matched game that I get from the Game name, I can find information for each thing:
- Main story
- Main + extra
- Completionist
- All styles
- Matched game name
- Similarity score

The similarity score is something I need to work with, as HLTB doesn't use steam's app ID information. You'll sometimes get very weird entries and that's something I needed to deal with.

## Then Machine Learning through SteamSpy Metadata

But as I was making this, I had an idea. What if I added a Machine Learning Algorithm to read your library then just recommend something on Steam? I haven't really figured out through what metrics yet, but the more data the better.

Hence, SteamSpy, where I was able to get the data that steam's doesn't supply

For each game I collect:
- Genres
- Tags
- Tag weights

This later became important for both filtering and the planned recommendation system.

## Saving Data

The data collected was originally in JSON. This was fine when it was just Steam, but as the amount of extra fields kept growing that obviously wouldn't last.

My library in particular contains thousands of games, and genres and tags naturally form many-to-many relationships. Repeated updates also meant rewriting a large amount of data. This was where a commit happened and thus was left with various different features left done but need work.

The whole GUI needed a design, but things could update, but only in batches and everything was created one by one so you update each category bit one by one as well. And my verification for your steam ID was asked at every interval in the terminal, which was fine before I included the GUI, but not so much afterwards.

<img src="Previous-SteamID-Ask.png" alt="Previous Verification" width="50%">

Because of the different intervels each API had and the amount of data that could be gotten, I had a few things I had to work on before I went further, hence phase 2.
