# Phase 4 - User Configuration & Application Hardening

Phase 4 is mostly about getting SteamLibraryData ready to behave like a normal desktop app instead of something that only works comfortably from the project folder.

The big goals were moving user data somewhere sensible, so getting rid of `.env` reliance, making account/API settings manageable from inside the app, and cleaning up how network failures are handled before packaging starts.

## Move User Data Out of the Project Folder

The database, settings, and cached images now live in the operating system's normal application-data directory instead of inside the repository.

That means the source folder stays cleaner and future packaged builds won't be trying to write user data next to the executable.

The old `games.json` cache system was also removed since SQLite has fully replaced it.

## Add Normal Application Settings

A small `settings.json` system was added for things like SteamID64.

The SteamID64 is now remembered as a regular app setting, while the database still stores which Steam account it belongs to.

That gives the app a default account without losing the safeguard that prevents two Steam libraries from being mixed together.

## Stop Using `.env` for the API Key

The old `.env` setup was removed.

Steam Web API keys are now stored through the operating system's credential manager using `keyring`.

The key no longer needs to sit in the project directory and is kept separate from both `settings.json` and the SQLite database.

## Add First-Run API Setup

If no Steam Web API key is configured, the app now asks for one directly.

The setup screen explains what kind of key is needed, links to Steam's API-key registration page, and makes it clear that SteamLibraryData does not need a Steam password or a Steamworks publisher key.

The key is also checked before being accepted, while network problems are treated separately from an actually invalid key.

## Make the Settings Tab Actually Manage Settings

The Settings tab used to mostly handle things like clearing cached images and resetting the database.

It can now also show and change the SteamID64 and replace the saved Steam Web API key.

Switching to a different Steam account resets the account-specific local database so data from two accounts cannot accidentally get mixed together.

The image cache can stay since Steam artwork is tied to App IDs rather than a particular account.

## Add Project and Support Links

The app now includes links back to the official project repository along with places for bug reports and general feedback.

This gives users somewhere obvious to go if something breaks or they have an idea, and also makes it easier to tell where the official copy of the project came from.

## Clean Up Steam API Errors

Steam requests now handle common failures in a much more readable way.

Instead of dumping raw networking errors at the user, the app can distinguish things like:

- a rejected API key
- no internet connection
- request timeouts
- Steam rate limiting
- Steam server problems
- unexpected response data

Failed Steam updates also leave existing local data alone instead of treating a failed request like valid empty data.

## Do the Same for SteamSpy and HowLongToBeat

SteamSpy and HowLongToBeat got the same general cleanup.

Temporary service or connection problems stay as failed updates so they can be retried later instead of being mistaken for valid missing metadata.

The existing HLTB matching system, retries, caching, Steam App ID checks, and manual review behavior were kept intact.
