# Phase 4 — User Configuration & Application Hardening

## Completed

- Moved user data out of the project directory into the OS application-data location.
- Centralized database and image-cache paths.
- Removed the obsolete `games.json` cache system.
- Added `settings.json` for normal user configuration.
- Added secure Steam Web API key storage using the operating system credential manager.
- Removed the `.env` dependency.
- Added first-run Steam API key setup and validation.
- SteamID64 is now persisted through the settings system while the database still tracks which Steam account owns its data.
- Added official repository/contact links and GitHub feedback/support links to the UI.

## Next

- Add SteamID64 and API-key management controls to the Settings tab.
- Improve Steam/network error handling.
- Update user-facing setup documentation.
- Perform a final Phase 4 cleanup/regression pass before packaging in Phase 5.