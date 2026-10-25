# Phase 6 - UI, Stability, Testing, and Distribution

Phase 6 focused on taking the completed application and preparing it for release. The main work was UI refinement, consistency fixes, cleanup, testing, audit tooling, and standalone Windows deployment.

## UI Improvements

The Library, Recommendations, and Maintenance areas received a broader polish pass.

Completed changes include:

- improved spacing, typography, and visual hierarchy
- reusable semantic UI components such as section headings, badges, and stat tiles
- alternating Library rows
- clearer sort-state behavior
- more responsive selected-game details
- improved trailer/media resizing
- vertical scrolling for recommendation media panels
- better behavior at smaller window sizes
- improved Maintenance cards and status presentation
- cleaner destructive/reset controls
- dark, light, and system appearance support
- dark mode as the default for new installs while preserving existing user preferences

Library filtering was also refined with:

- separate game and software genre groups
- `Unknown (Game)` and `Unknown (Software)`
- Test/Beta classification
- `Free To Play` genre normalization
- improved backlog eligibility handling

Per-title refresh actions were retained for HLTB, metadata, and achievements so stale data can be updated without running a full-library refresh.

## Classification and Maintenance Consistency

Game classification and backlog eligibility were centralized into shared logic.

This fixed cases where the Library could interpret an entry as software or a Test/Beta build while Maintenance still treated it as a normal backlog game.

The same effective classification is now used by:

- Library filtering
- Steam type display
- HLTB update selection
- achievement update selection
- missing-data counts
- Maintenance workflows

Metadata updates remain broader because metadata is needed to classify unknown entries in the first place.

The stale-data workflow was also improved so HLTB, metadata, and achievements can be refreshed based on age or changed playtime rather than only filling completely missing data.

## Testing

The pytest suite was expanded and cleaned up to focus on meaningful regression coverage.

Current tests cover areas such as:

- recommendation feature construction
- feedback and preference modeling
- neighbor and similar-game ranking
- ratings and database persistence
- Steam API parsing
- Game status behavior
- Test/Beta detection
- effective Steam classification
- backlog eligibility
- update-controller candidate selection
- database round trips
- important Maintenance behavior
- recommendation scrolling and UI regressions

Tests use temporary databases and offscreen Qt where appropriate, keeping them isolated from the real user library.

## Audit and Diagnostic Tools

The previous collection of Phase 5 audit scripts was consolidated into a smaller toolset:

```text
tools/
├── database_audit.py
├── recommendation_audit.py
├── recommendation_evaluation.py
└── recommendation_inspect.py
```

These cover:

- SQLite integrity
- foreign-key integrity
- classification and maintenance coverage
- HLTB and achievement consistency
- orphaned database data
- recommendation structural correctness
- recommendation model evaluation
- manual recommendation inspection

The database and recommendation audits complement pytest by checking the real library rather than only synthetic test data.

## Code Cleanup

Release preparation also removed or consolidated obsolete code.

Completed cleanup includes:

- removal of `backlog.py`
- removal of unused worker classes
- removal of dead database helpers
- consolidation of shared widgets
- centralized classification logic
- consolidation of duplicate audit scripts
- cleanup of stale update logic
- removal of older implementation remnants discovered during regression testing

## Distribution

Windows deployment was completed using PySide6 deployment tooling and Nuitka.

Working builds were produced in both forms:

- distribution-folder build
- one-file executable

Deployment work also covered:

- application icon
- Qt dependencies
- Qt Multimedia
- FFmpeg support
- standalone launch verification
- Windows dependency inspection

The packaged application was tested outside the normal development run path and confirmed to launch successfully.

The current release format is portable rather than a traditional installer.
