/* The workspace timeline: replays a lifecycle log as a Metro timeline of nodes on one Canvas2D.
   A classic script with no library and no build step. The pure part (fold, layout, playhead step) touches
   no DOM, so node can require() it; mount() is the browser shell around it. All times are epoch ms. */
(function (root) {
  'use strict';

  const DAY = 86400000;
  const HOUR = 3600000;

  // --- status classes ----------------------------------------------------------
  const WARN_STATUSES = ['blocked', 'drifted', 'superseded', 'abandoned', 'failed'];
  const REVIEW_STATUSES = ['judging', 'checking', 'shipping', 'verified'];

  // The first rule that matches decides, so a finish status named like a warning still reads as one.
  function statusClass(status, typeInfo) {
    if (WARN_STATUSES.includes(status)) return 'warn';
    if (typeInfo && typeInfo.finish.includes(status)) return 'done';
    if (/review/i.test(status) || REVIEW_STATUSES.includes(status)) return 'review';
    if (typeInfo && status === typeInfo.initial) return 'idle';
    return 'active';
  }

  // --- the player's clock --------------------------------------------------------
  // Stretches with nothing near the playhead pass six times faster.
  function playheadStep(T, dtSeconds, speedDaysPerSecond, nextEventTs) {
    const boost = nextEventTs !== null && nextEventTs - T > 6 * HOUR ? 6 : 1;
    return T + dtSeconds * speedDaysPerSecond * DAY * boost;
  }

  const PastaTimeline = { statusClass, playheadStep };
  root.PastaTimeline = PastaTimeline;
  if (typeof module !== 'undefined' && module.exports) module.exports = PastaTimeline;
})(typeof globalThis !== 'undefined' ? globalThis : this);
