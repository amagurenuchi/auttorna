# Estimated gameplay geometry

These values were estimated from the supplied 2880x1920 screenshot and are
stored in `config.json`.

The current capture source is a window capture. Therefore `roi` is relative to
the captured Etterna window, and `lanes`/`receptor_y` are relative to the ROI.
They are not absolute desktop coordinates.

Estimated values:

- window bounds: approximately `(160, 206)` to `(2720, 1705)`;
- ROI relative to the window: `[790, 54, 900, 1390]`;
- lane centers in desktop coordinates: approximately `1150, 1345, 1535, 1727`;
- lane bounds in ROI coordinates: `[105,299]`, `[300,490]`, `[491,681]`,
  `[682,873]`;
- receptor Y in ROI coordinates: approximately `1215`;
- configured display refresh: `120 Hz`.

The geometry should be verified with a live capture preview. Window borders,
title-bar height, Windows display scaling, and Etterna layout changes can shift
these values. The same geometry should remain usable at 60 Hz; refresh rate
changes timing cadence, not these screen coordinates.

Live capture verification returned a physical-pixel frame of `1390x900` after
the ROI was applied, so the supplied 2880x1920 coordinate scale is currently
compatible with capture. The configured title substring matched
`Etterna - File Explorer` during verification; select the exact Etterna game
window from the GUI window list before using the capture or input path.

Lane scan codes are intentionally not populated here. They should be selected
through the input-binding UI once the predictive scheduler is integrated.
