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

  // --- fold: the served events into one record per page ----------------------------
  // Each record keeps its title, parent, status and own archived flag as segments {t, v} in event order,
  // so the value at any moment is a binary search.
  function segmentAt(segments, T) {
    let lo = 0, hi = segments.length - 1, found = -1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (segments[mid].t <= T) { found = mid; lo = mid + 1; } else hi = mid - 1;
    }
    return found < 0 ? null : segments[found];
  }
  function valueAt(p, segments, T) {
    if (T < p.born) return null;
    const segment = segmentAt(segments, T);
    return segment ? segment.v : null;
  }
  function statusAt(p, T) { return valueAt(p, p.statuses, T); }
  function titleAt(p, T) { return valueAt(p, p.titles, T); }
  function parentAt(p, T) { return valueAt(p, p.parents, T); }
  function archivedAt(p, T) { return valueAt(p, p.archived, T) === true; }

  function isFinish(types, type, status) {
    const info = types[type];
    return !!info && info.finish.includes(status);
  }

  function activityOf(event, elements) {
    const list = elements[event.section + '.' + event.field];
    if (event.kind === 'el_added') return list === 'Question' ? 'asked' : 'edit';
    if (event.kind === 'el_status') {
      if (list === 'Question' && event.to === 'answered') return 'answered';
      if (list === 'Step' && event.to === 'done') return 'step';
      if (list === 'Case' && event.to === 'passed') return 'case';
    }
    return 'edit';
  }

  function fold(data) {
    const types = (data && data.types) || {};
    const events = (data && Array.isArray(data.events)) ? data.events : [];
    const pages = [], byId = new Map(), links = [], gaps = [], eventTs = [];
    const childCount = new Map();
    let recordingStart = null, knownAtBaseline = null;
    const namedAtBaseline = new Set();

    function newPage(event, t, present) {
      const parent = event.parent === undefined ? null : event.parent;
      const kidIndex = childCount.get(parent) || 0;
      childCount.set(parent, kidIndex + 1);
      const p = {
        id: event.page, type: event.type, born: t, present, finishT: null, endedAt: null, deleted: false, kidIndex,
        titles: [{ t, v: event.title }], parents: [{ t, v: parent }], statuses: [{ t, v: event.status }],
        archived: [{ t, v: present ? event.archived === true : false }], marks: [], acts: [],
        trunk: false, track: null, y: null, lane0: null, lane1: null, shown: [], branchY: null, settleY: null,
      };
      byId.set(p.id, p);
      pages.push(p);
      return p;
    }
    function openLinks(pageId) {
      return links.filter(link => link.a === pageId && link.until === Infinity);
    }
    function setIfChanged(segments, t, value) {
      if (segments[segments.length - 1].v !== value) segments.push({ t, v: value });
    }

    for (const event of events) {
      if (!event || typeof event !== 'object' || typeof event.ts !== 'number') continue;
      const t = event.ts;
      eventTs.push(t);
      if (event.kind === 'gap') { gaps.push({ t, missing: event.missing, seq: event.seq }); continue; }
      if (event.kind === 'created') {
        if (!byId.has(event.page)) {
          const p = newPage(event, t, false);
          p.marks.push({ t, k: 'created', s: event.status });
        }
        continue;
      }
      if (event.kind === 'present') {
        if (recordingStart === null) { recordingStart = t; knownAtBaseline = Array.from(byId.keys()); }
        namedAtBaseline.add(event.page);
        const listed = Array.isArray(event.links) ? event.links : [];
        let p = byId.get(event.page);
        if (!p) {
          p = newPage(event, t, true);
          for (const link of listed) links.push({ a: p.id, b: link.to, role: link.role, t, until: Infinity });
          if (isFinish(types, p.type, event.status)) p.finishT = t;
          continue;
        }
        if (p.deleted) continue;
        // A page the back-fill already holds takes the recorded values silently from this instant.
        setIfChanged(p.titles, t, event.title);
        setIfChanged(p.parents, t, event.parent === undefined ? null : event.parent);
        setIfChanged(p.statuses, t, event.status);
        setIfChanged(p.archived, t, event.archived === true);
        const wanted = new Set(listed.map(link => link.to + '\n' + link.role));
        const open = openLinks(p.id);
        for (const link of open) if (!wanted.has(link.b + '\n' + link.role)) link.until = t;
        const have = new Set(open.map(link => link.b + '\n' + link.role));
        for (const link of listed) {
          if (!have.has(link.to + '\n' + link.role)) links.push({ a: p.id, b: link.to, role: link.role, t, until: Infinity });
        }
        if (p.finishT === null && isFinish(types, p.type, event.status)) p.finishT = t;
        continue;
      }
      const p = byId.get(event.page);
      if (!p || p.deleted) continue;
      const info = types[p.type];
      switch (event.kind) {
        case 'status': {
          p.statuses.push({ t, v: event.to });
          const gate = !!info && info.gates.some(edge => edge[0] === event.from && edge[1] === event.to);
          if (p.finishT === null && isFinish(types, p.type, event.to)) {
            p.finishT = t;
            p.marks.push({ t, k: 'ship', s: event.to, gate });
          } else p.marks.push({ t, k: 'status', s: event.to, gate });
          break;
        }
        case 'renamed': p.titles.push({ t, v: event.title }); p.marks.push({ t, k: 'rename' }); break;
        case 'moved': p.parents.push({ t, v: event.to_parent }); p.marks.push({ t, k: 'move' }); break;
        case 'linked': links.push({ a: p.id, b: event.to, role: event.role, t, until: Infinity }); break;
        case 'unlinked': {
          for (let i = links.length - 1; i >= 0; i--) {
            const link = links[i];
            if (link.a === p.id && link.b === event.to && link.role === event.role && link.until === Infinity) {
              link.until = t;
              break;
            }
          }
          break;
        }
        case 'archived': p.archived.push({ t, v: true }); p.marks.push({ t, k: 'archive' }); break;
        case 'unarchived': p.archived.push({ t, v: false }); p.marks.push({ t, k: 'unarchive' }); break;
        case 'deleted': p.endedAt = t; p.deleted = true; p.marks.push({ t, k: 'delete' }); break;
        case 'edited': case 'el_added': case 'el_status': case 'el_edited': case 'el_removed':
          p.acts.push({ t, w: activityOf(event, info ? info.elements : {}) });
          break;
        default: break;
      }
    }
    // What the baseline does not name was gone by the time recording started.
    if (knownAtBaseline !== null) {
      for (const id of knownAtBaseline) {
        if (namedAtBaseline.has(id)) continue;
        const p = byId.get(id);
        p.endedAt = p.endedAt === null ? recordingStart : Math.min(p.endedAt, recordingStart);
      }
    }
    eventTs.sort((a, b) => a - b);
    return {
      pages, byId, types, recordingStart, gaps, eventTs,
      links: links.filter(link => byId.has(link.a) && byId.has(link.b)),
      t0: data && typeof data.t0 === 'number' ? data.t0 : null,
      t1: data && typeof data.t1 === 'number' ? data.t1 : null,
    };
  }

  // The wiki's own subtree rule: hidden while the page or any ancestor it has at T is archived.
  function isShown(m, p, T) {
    if (T < p.born) return false;
    if (p.endedAt !== null && p.endedAt <= T) return false;
    let q = p;
    for (let depth = 0; q && depth < 64; depth++) {
      if (archivedAt(q, T)) return false;
      const parentId = parentAt(q, T);
      q = parentId === null ? null : m.byId.get(parentId);
    }
    return true;
  }

  // --- Metro layout: trunks for root pages, a branch per page that merges back on finish ------
  const TRACK_PITCH = 17;
  const LAYOUT_PAD = 20;
  const TRUNK_SPACING = 24;
  const TRACK_RELEASE = 30 * 60000;

  // isShown only changes where the page's or one of its ever-ancestors' parent or archived flag does,
  // so evaluating it at those instants gives the exact intervals.
  function shownIntervals(m, p) {
    const instants = new Set([p.born]);
    if (p.endedAt !== null) instants.add(p.endedAt);
    const visited = new Set();
    const pending = [p];
    while (pending.length) {
      const q = pending.pop();
      if (visited.has(q.id)) continue;
      visited.add(q.id);
      instants.add(q.born);
      for (const segment of q.archived) instants.add(segment.t);
      for (const segment of q.parents) {
        instants.add(segment.t);
        const parent = segment.v === null ? undefined : m.byId.get(segment.v);
        if (parent) pending.push(parent);
      }
    }
    const sorted = Array.from(instants).filter(t => t >= p.born).sort((a, b) => a - b);
    const intervals = [];
    for (let i = 0; i < sorted.length; i++) {
      if (!isShown(m, p, sorted[i])) continue;
      const to = i + 1 < sorted.length ? sorted[i + 1] : Infinity;
      const last = intervals[intervals.length - 1];
      if (last && last[1] === sorted[i]) last[1] = to; else intervals.push([sorted[i], to]);
    }
    return intervals;
  }

  // The row a page is drawn on at t: its own track until it finishes, then wherever its parent is.
  function rowAt(m, p, t, depth) {
    if (!p || depth > 64) return null;
    if (p.trunk) return p.track;
    if (p.track !== null && (p.finishT === null || t < p.finishT)) return p.track;
    const parentId = parentAt(p, t);
    const row = rowAt(m, parentId === null ? undefined : m.byId.get(parentId), t, depth + 1);
    return row !== null ? row : p.track;
  }

  function layoutMetro(m) {
    const t1 = m.t1 === null ? Infinity : m.t1;
    const trunkRows = new Set();
    const freeFrom = new Map();
    let trunkCount = 0;
    for (const p of m.pages) {
      p.shown = shownIntervals(m, p);
      p.trunk = false; p.track = null; p.lane0 = null; p.lane1 = null;
      if (p.shown.length === 0) continue;
      const lastShownEnd = p.shown[p.shown.length - 1][1];
      const parentId = parentAt(p, p.born);
      const parent = parentId === null ? undefined : m.byId.get(parentId);
      if (!parent) {
        const k = trunkCount++;
        p.trunk = true;
        p.track = (k % 2 ? 1 : -1) * Math.ceil(k / 2) * TRUNK_SPACING;
        trunkRows.add(p.track);
        p.lane0 = p.born;
        p.lane1 = lastShownEnd === Infinity ? t1 : lastShownEnd;
        continue;
      }
      if (p.present && p.finishT === p.born) continue;   // settled from the moment it is first seen
      const parentRow = rowAt(m, parent, p.born, 0);
      const from = parentRow === null ? 0 : parentRow;
      const side = p.kidIndex % 2 ? -1 : 1;
      let track = null;
      for (let k = 1; track === null; k++) {
        const candidate = from + (k % 2 ? side : -side) * Math.ceil(k / 2);
        if (trunkRows.has(candidate)) continue;
        const free = freeFrom.get(candidate);
        if (free === undefined || free <= p.born) track = candidate;
      }
      p.track = track;
      p.lane0 = p.born;
      p.lane1 = p.finishT !== null ? p.finishT : (lastShownEnd === Infinity ? t1 : lastShownEnd);
      freeFrom.set(track, p.lane1 < t1 ? p.lane1 + TRACK_RELEASE : Infinity);
    }

    let minRow = 0, maxRow = 0;
    for (const p of m.pages) {
      if (p.track === null) continue;
      minRow = Math.min(minRow, p.track);
      maxRow = Math.max(maxRow, p.track);
    }
    const rowY = row => row === null ? null : (row - minRow) * TRACK_PITCH + LAYOUT_PAD;
    const pageRowY = (p, t) => rowY(rowAt(m, p, t, 0));
    for (const p of m.pages) {
      p.y = rowY(p.track);
      const parentId = parentAt(p, p.born);
      const parent = parentId === null ? undefined : m.byId.get(parentId);
      p.branchY = parent ? pageRowY(parent, p.born) : null;
      if (p.finishT !== null) {
        const finishParentId = parentAt(p, p.finishT);
        const finishParent = finishParentId === null ? undefined : m.byId.get(finishParentId);
        p.settleY = finishParent ? pageRowY(finishParent, p.finishT) : null;
      } else p.settleY = null;
      for (const mark of p.marks) mark.y = mark.k === 'ship' && p.track !== null ? p.y : pageRowY(p, mark.t);
      for (const act of p.acts) act.y = pageRowY(p, act.t);
    }
    for (const link of m.links) {
      link.ya = pageRowY(m.byId.get(link.a), link.t);
      link.yb = pageRowY(m.byId.get(link.b), link.t);
    }
    return { height: (maxRow - minRow) * TRACK_PITCH + 2 * LAYOUT_PAD };
  }

  const PastaTimeline = { statusClass, playheadStep, fold, isShown, statusAt, titleAt, parentAt, layoutMetro };
  root.PastaTimeline = PastaTimeline;
  if (typeof module !== 'undefined' && module.exports) module.exports = PastaTimeline;
})(typeof globalThis !== 'undefined' ? globalThis : this);
