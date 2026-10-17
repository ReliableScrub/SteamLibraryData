# Phase 4 - User Configuration & Application Hardening

Phase 4 was about getting SteamLibraryData to behave more like a normal desktop application instead of something that only works comfortably from the project folder.

Most of the work was behind the scenes: moving user data, replacing development-only configuration, improving first-run setup, hardening external API failures, and cleaning up the repository before moving on to larger user-facing features.

## Move User Data Out of the Project Folder

The database, settings, and cached images were moved out of the repository and into the operating system's normal application-data directory.

SteamLibraryData now stores its local data in:

- Windows: `%APPDATA%\SteamLibraryData`
- macOS: `~/Library/Application Support/SteamLibraryData`
- Linux: `$XDG_DATA_HOME/SteamLibraryData` or `~/.local/share/SteamLibraryData`

This keeps user data separate from the source code and avoids future packaged builds trying to write next to the executable.

The old `games.json` cache was also removed since SQLite had already replaced it.

## Add Proper Steam Account Configuration

The old `.env` configuration was removed.

SteamID64 is now stored as a normal application setting in `settings.json`, while the SQLite database still records which Steam account its data belongs to.

This keeps the configured account easy to remember while still preventing two different Steam libraries from accidentally being mixed into the same database.

The Steam Web API key is stored separately through the operating system's credential manager using `keyring`.

It is not stored in:

- `settings.json`
- the SQLite database
- the project directory

The application also no longer depends on `python-dotenv`.

### First-Run Steam Setup

The original first-run setup asked for SteamID64 and the API key separately.

That worked, but it could leave the app partially configured if the user completed one prompt and cancelled the other.

This was replaced with one combined Steam setup screen.

The user now enters:

- SteamID64
- Steam Web API key

Both values are verified before anything is saved.

The application checks that:

- the SteamID64 is numeric
- the API key is accepted by Steam
- the SteamID64 actually belongs to a Steam account

If validation fails, the setup stays open and nothing new is saved.

If setup is cancelled, the main application does not open.

Once both values have been verified successfully, they are saved and the main window can start.

### Keep Data Collection User-Controlled

Completing Steam setup does not automatically start importing or updating everything.

If the database is empty, SteamLibraryData asks whether the user wants to import their Steam library.

The user can decline and continue using the application without starting an import.

SteamSpy, HowLongToBeat, achievement updates, Steam classification, and other bulk data updates are also started manually.

SteamLibraryData does not continuously monitor a Steam account or automatically run bulk updates simply because the application is open.

## Improve the Settings Tab

The Settings tab was expanded so Steam configuration can be managed without editing files manually.

Users can now:

- view the configured SteamID64
- change the SteamID64
- replace the Steam Web API key
- clear the image cache
- reset the local database

Changing the SteamID64 verifies the new account before anything is changed.

If the current database belongs to another Steam account, the application warns that switching accounts requires deleting the old account-specific database.

The image cache can remain because Steam artwork is tied to App IDs rather than a specific account.

Changing the API key also validates the replacement key against the configured Steam account before saving it.

## Add Project and Support Links

A Contact tab was added with links to the official project resources.

It includes:

- the GitHub repository
- GitHub Discussions
- GitHub Issues
- optional project support

This gives users an obvious place to report bugs, give feedback, or confirm where the official project came from.

## Improve External Service Error Handling

Steam, SteamSpy, and HowLongToBeat were all given clearer failure handling.

The application can now distinguish failures such as:

- invalid or rejected credentials
- connection failures
- request timeouts
- rate limiting
- server failures
- malformed or unexpected responses

The important change is that failed requests are no longer treated like successful requests that simply returned no data.

Existing local data is preserved when an external service fails.

### Steam

Steam API requests now return clearer messages for common failures such as rejected API keys, connection problems, rate limits, and Steam outages.

Account validation also uses Steam directly so invalid SteamID64 values can be rejected before being saved.

### SteamSpy

SteamSpy now distinguishes legitimate empty metadata from temporary service failures or malformed responses.

A failed request therefore does not incorrectly mark a game as having no genre or tag information.

### HowLongToBeat

The existing HowLongToBeat matching system was mostly left intact.

Retries, caching, Steam App ID verification, conservative automatic matching, and manual review continue to work as before.

The main change was making sure repeated connection failures remain actual failed updates instead of eventually being mistaken for valid no-match results.