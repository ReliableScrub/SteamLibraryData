# SteamLibraryData - Post-v1.0 Progress

**Baseline:** v1.0.0  
**Current checkpoint:** Post-1.0 work, before v1.1.0

## Done since 1.0

### Steam / classification

- Added better local Steam classification support.
- Added local `appinfo.vdf` parsing.
- Added Test / Beta handling.
- Added Bonus Content handling.
- Added local private-app detection as advisory information.
- Centralized backlog eligibility around the shared classifier.
- Excluded software, DLC, video, hardware, test builds, and similar entries from normal backlog enrichment.

### Maintenance

- `Update Missing Data` now runs classification first.
- HLTB, metadata, and achievements run after classification.
- Missing-data updates and stale-data refreshes stay separate.
- Added better batch failure reporting.
- Added selected-game refresh buttons.
- Added multi-select refresh from the Library right-click menu.
- Prevented selected refreshes from starting while Maintenance is already busy.
- Improved syncing between Library game objects and Maintenance game objects.
- Kept update cancellation and incremental database saves working.

### HLTB

- Removed the large project-side HLTB alias table.
- Reworked matching around:
  - conservative title matching;
  - broader discovery searches;
  - Steam AppID verification.
- Added more general title cleanup instead of one-off game exceptions.
- Added handling for:
  - trademark/legal markers;
  - punctuation differences;
  - Greek symbols such as `Σ`;
  - Roman/Arabic installment numbering;
  - edition/remaster wording;
  - subtitle/title-fragment discovery.
- Exact Steam AppID matches are preferred when HLTB exposes them.
- Broader title reductions no longer prove identity on their own.
- Expensive HLTB detail-page verification is bounded.
- Selected HLTB refreshes now do a real fresh lookup instead of reusing stale process cache.
- Selected HLTB refresh state now stays in sync between Library and Maintenance.

### Manual HLTB matching

- Added **Set HLTB Match...**
- Accepts:
  - an HLTB game URL;
  - a numeric HLTB game ID.
- Shows the HLTB title and completion times before accepting.
- Checks the HLTB Steam AppID when available.
- Warns on missing or mismatched Steam AppIDs.
- Still allows a manual override when the user intentionally confirms it.
- Saves through the normal HLTB persistence path.

### HLTB status labels

- `Not Checked`
  - eligible game;
  - no completed HLTB lookup yet.
- `Review`
  - possible candidates found;
  - no safe automatic match.
- `Not Found`
  - lookup completed;
  - no usable match found.
- `Skipped`
  - intentionally excluded from HLTB/backlog processing.
- `N/A`
  - matched HLTB page;
  - selected metric has no value.
- `X.X h`
  - normal matched HLTB value.

### Achievement handling

- Improved achievement refresh reliability.
- Added better fallback behavior around unavailable/private Steam data.
- Avoided replacing valid positive achievement data with weak/ambiguous zero results.
- Added clearer failure reporting.

### Library

- Added multi-row selection.
- Added right-click **Refresh Selected**.
- Kept movable/resizable/hideable columns.
- Kept saved column/layout preferences.
- Added display-size options.
- Improved category/filter card sizing.
- Added live HLTB and achievement cell refresh during background updates.
- Preserved horizontal and vertical scroll position during full table refreshes.

## Current HLTB flow

- Start with the Steam library title.
- Try conservative identity searches.
- Prefer exact Steam AppID evidence when available.
- Fall back to broader discovery searches.
- Require stronger verification for aggressive title reductions.
- If no safe automatic match exists:
  - send it to Review;
  - mark it Not Found;
  - or manually assign the HLTB page.

## Current Maintenance behavior

- Classification runs first.
- Only backlog-eligible entries are considered for normal HLTB work.
- Excluded entries show `Skipped` instead of `Not Checked`.
- Missing data and stale data are treated separately.
- Maintenance counts should now agree with Library HLTB states.

## Still to do

- Fix achievement sorting so `Unknown`, `None`, and numeric progress sort separately.
- Make Recommendations rebuild automatically when entering the tab if needed and Maintenance is idle.
- Add Up/Down arrow navigation through Library rows.
- Keep testing HLTB misses/review cases against the real library.