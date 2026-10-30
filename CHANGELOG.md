# Changelog

All notable changes to SteamLibraryData will be documented in this file.

## [Unreleased]

### Added
- Added F1 shortcut for Help / FAQ.
- Added F5 shortcut for Steam Library refresh.
- Added Launch Game and Launch in Steam actions.
- Added bulk status and rating changes.
- Added right-click copy actions for Steam and HLTB information.
- Added persistent startup update preferences.
- Added Retry Failed for failed HLTB, metadata, and achievement updates.
- Added manual local database backups.
- Added validated database restore with automatic pre-restore safety backups.
- Added automatic safety backups before resetting the local database.
- Added Open Data Folder from Maintenance.
- Added Copy Diagnostic Info for troubleshooting and bug reports.
- Added protection against restoring invalid databases or databases belonging to a different Steam account.

### Changed
- Recommendations now rebuild automatically when needed on tab entry.
- Recommendation rebuilds are deferred while Maintenance is running.
- Multiple recommendation-relevant changes are coalesced into one rebuild.
- Maintenance progress rows now keep a stable layout while showing the current game.
- Long game names are elided instead of shrinking progress bars.
- Update Missing Data now performs Steam classification before enrichment.
- HLTB matching now uses broader discovery with conservative identity verification.
- Selected HLTB refreshes perform fresh lookups instead of reusing cached searches.
- Database backup and restore now use SQLite-safe backup handling.
- Automatic safety backups now use unique filenames so existing backups are not silently overwritten.
- Database restore now validates the minimum required SteamLibraryData schema before replacing the current database.
- Database restore now closes the application after replacement so data can be reloaded cleanly.
- Reset Local Database now gives a clearer explanation of what data will be removed and preserved.
- Diagnostic information now includes useful application, database, runtime, and configuration details without exposing the Steam Web API key.
- Library genre and tag associations are now loaded in bulk instead of issuing separate queries for every game.
- Settings are now written atomically to reduce the chance of corruption during a save.
- Malformed settings files are preserved for recovery instead of being silently overwritten.
- Maintenance database actions are locked while selected-game refreshes or manual HLTB matching are actively using the database.
- Colored action buttons now visibly use the disabled style when unavailable.

### Fixed
- Fixed achievement sorting so numeric progress, `None`, and `Unknown` sort separately.
- Fixed Library keyboard navigation with Up, Down, Home, and End.
- Fixed scroll-position loss during full Library refreshes.
- Fixed synchronization between selected-game HLTB refreshes and Maintenance data.
- Prevented unnecessary recommendation rebuilds after unchanged Steam library refreshes.
- Prevented database restore or reset from running while selected-game refreshes or manual HLTB matching are still writing local data.
- Prevented automatic safety backups created in rapid succession from overwriting one another.
- Improved restore validation so incomplete SQLite databases with missing required columns are rejected.
- Fixed custom primary, warning, and danger button styles overriding the normal disabled appearance.