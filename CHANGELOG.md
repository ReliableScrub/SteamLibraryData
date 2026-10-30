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

### Changed
- Recommendations now rebuild automatically when needed on tab entry.
- Recommendation rebuilds are deferred while Maintenance is running.
- Multiple recommendation-relevant changes are coalesced into one rebuild.
- Maintenance progress rows now keep a stable layout while showing the current game.
- Long game names are elided instead of shrinking progress bars.
- Update Missing Data now performs Steam classification before enrichment.
- HLTB matching now uses broader discovery with conservative identity verification.
- Selected HLTB refreshes perform fresh lookups instead of reusing cached searches.

### Fixed
- Fixed achievement sorting so numeric progress, `None`, and `Unknown` sort separately.
- Fixed Library keyboard navigation with Up, Down, Home, and End.
- Fixed scroll-position loss during full Library refreshes.
- Fixed synchronization between selected-game HLTB refreshes and Maintenance data.
- Prevented unnecessary recommendation rebuilds after unchanged Steam library refreshes.