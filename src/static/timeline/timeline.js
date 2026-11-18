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

  // --- the browser shell: canvas drawing ----------------------------------------------------
  const AXIS = 26;          // height of the axis band above the stage, px
  const BAR = 3;            // status bar thickness, px
  const BRANCH = 22;        // width of a branch or merge curve, px
  const FONT = '11px system-ui, -apple-system, "Segoe UI", sans-serif';
  const BOLD_FONT = '600 11px system-ui, -apple-system, "Segoe UI", sans-serif';
  const SMALL_FONT = '10px system-ui, -apple-system, "Segoe UI", sans-serif';
  const FOLLOW_AT = 0.62;   // where the playhead stands while the view follows it
  const START_SPAN = 3 * DAY;
  const SHAPES = { 'feature-brief': 'circle', 'simple-change': 'circle', 'bug-report': 'circle', epic: 'hexagon',
    toc: 'bar', architecture: 'triangle', document: 'triangle', 'decision-record': 'triangle' };
  const ACTIVITY_COLOURS = { asked: 'review', answered: 'review', step: 'active', case: 'done', edit: 'muted' };
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const GRID_STEPS = [HOUR, 6 * HOUR, DAY, 7 * DAY, 30 * DAY];

  const pad2 = n => String(n).padStart(2, '0');
  function formatDay(t) { const d = new Date(t); return d.getUTCDate() + ' ' + MONTHS[d.getUTCMonth()]; }
  function formatMoment(t) {
    const d = new Date(t);
    return formatDay(t) + ' ' + d.getUTCFullYear() + ' ' + pad2(d.getUTCHours()) + ':' + pad2(d.getUTCMinutes());
  }
  function formatHour(t) { return pad2(new Date(t).getUTCHours()) + ':00'; }

  function readColours() {
    const style = getComputedStyle(document.body);
    const read = name => style.getPropertyValue(name).trim();
    return {
      background: read('--background-body'), panel: read('--background'), text: read('--text-main'),
      muted: read('--text-muted'), border: read('--border'),
      idle: read('--tl-idle'), active: read('--tl-active'), review: read('--tl-review'), done: read('--tl-done'),
      warn: read('--tl-warn'), archived: read('--tl-archived'), gate: read('--tl-gate'), link: read('--tl-link'),
      accent: read('--tl-accent'),
    };
  }

  // Index of the first item whose t is >= t.
  function firstAtOrAfter(items, t) {
    let lo = 0, hi = items.length;
    while (lo < hi) { const mid = (lo + hi) >> 1; if (items[mid].t < t) lo = mid + 1; else hi = mid; }
    return lo;
  }
  function shownAt(p, t) {
    for (const interval of p.shown) if (interval[0] <= t && t < interval[1]) return true;
    return false;
  }
  function lastShownEnd(p) { return p.shown.length ? p.shown[p.shown.length - 1][1] : p.born; }

  function glyph(c, shape, x, y, r) {
    c.beginPath();
    if (shape === 'circle') c.arc(x, y, r, 0, 2 * Math.PI);
    else if (shape === 'triangle') { c.moveTo(x, y - r - 1); c.lineTo(x + r + 1, y + r); c.lineTo(x - r - 1, y + r); c.closePath(); }
    else if (shape === 'hexagon') {
      for (let i = 0; i < 6; i++) {
        const a = Math.PI / 3 * i;
        if (i) c.lineTo(x + Math.cos(a) * (r + 1), y + Math.sin(a) * (r + 1)); else c.moveTo(x + r + 1, y);
      }
      c.closePath();
    } else if (shape === 'bar') c.rect(x - 2, y - 5, 4, 10);
    else c.rect(x - r, y - r, r * 2, r * 2);
    c.fill();
  }

  function createViewer(root, m, layout) {
    const stage = root.querySelector('#tl-stage'), overview = root.querySelector('#tl-overview');
    const stageContext = stage.getContext('2d'), overviewContext = overview.getContext('2d');
    const t0 = m.t0, t1 = m.t1;
    const view = { width: 0, height: 0, overviewWidth: 0, overviewHeight: 0, dpr: 1, colours: readColours() };
    const S = { T: t0, playing: false, speed: 0.25, follow: true, ghost: true, span: START_SPAN,
      x0: t0 - FOLLOW_AT * START_SPAN, y0: 0, cameraSet: false, hover: null, dirty: true };

    // Everything drawn is static after the layout, so it is indexed by time once.
    const lanes = m.pages.filter(p => p.track !== null);
    const marks = [], acts = [], touches = [];
    for (const p of m.pages) {
      for (const mark of p.marks) if (mark.y !== null) { marks.push({ t: mark.t, mark, p }); touches.push({ t: mark.t, y: mark.y }); }
      for (const act of p.acts) if (act.y !== null) { acts.push({ t: act.t, act, p }); touches.push({ t: act.t, y: act.y }); }
      if (p.track !== null) touches.push({ t: p.lane0, y: p.y });
    }
    const byTime = (a, b) => a.t - b.t;
    marks.sort(byTime); acts.sort(byTime); touches.sort(byTime);
    const settled = m.pages.filter(p => p.finishT !== null && p.settleY !== null).sort((a, b) => a.finishT - b.finishT);
    let settledHits = [];
    let overviewCache = null;

    function size() {
      const dpr = window.devicePixelRatio || 1;
      const box = stage.getBoundingClientRect(), overviewBox = overview.getBoundingClientRect();
      view.dpr = dpr;
      view.width = box.width; view.height = box.height;
      view.overviewWidth = overviewBox.width; view.overviewHeight = overviewBox.height;
      stage.width = Math.round(box.width * dpr); stage.height = Math.round(box.height * dpr);
      overview.width = Math.round(overviewBox.width * dpr); overview.height = Math.round(overviewBox.height * dpr);
      overviewCache = null;
      S.dirty = true;
    }
    function recolour() { view.colours = readColours(); overviewCache = null; S.dirty = true; }

    const scale = () => view.width / S.span;
    const X = t => (t - S.x0) * scale();
    const Y = y => y - S.y0 + AXIS;
    const crisp = v => Math.round(v) + 0.5;

    function statusColour(p, status) {
      return view.colours[statusClass(status, m.types[p.type])];
    }

    function drawConnectors(c, v0, v1, T) {
      const colours = view.colours;
      const solid = new Path2D(), ghost = new Path2D();
      const margin = (BRANCH + 10) / scale();
      for (const p of lanes) {
        if (p.trunk) continue;
        if (p.branchY !== null && p.lane0 > v0 - margin && p.lane0 < v1 + margin && shownAt(p, p.lane0)) {
          const path = p.lane0 <= T ? solid : ghost;
          const x = X(p.lane0), ya = Y(p.branchY), yb = Y(p.y);
          path.moveTo(x - BRANCH, ya);
          path.bezierCurveTo(x - BRANCH / 2, ya, x - BRANCH / 2, yb, x, yb);
        }
        if (p.finishT !== null && p.settleY !== null && p.finishT > v0 - margin && p.finishT < v1 + margin && shownAt(p, p.finishT)) {
          const path = p.finishT <= T ? solid : ghost;
          const x = X(p.finishT), ya = Y(p.y), yb = Y(p.settleY);
          path.moveTo(x, ya);
          path.bezierCurveTo(x + BRANCH / 2, ya, x + BRANCH / 2, yb, x + BRANCH, yb);
        }
      }
      c.lineWidth = 1;
      c.strokeStyle = colours.border;
      c.stroke(solid);
      if (S.ghost) { c.globalAlpha = 0.35; c.strokeStyle = colours.muted; c.stroke(ghost); c.globalAlpha = 1; }
    }

    function drawLinks(c, T) {
      const colours = view.colours, hover = S.hover;
      for (const link of m.links) {
        if (link.ya === null || link.yb === null) continue;
        const x = X(link.t);
        if (x < -80 || x > view.width + 80) continue;
        const a = m.byId.get(link.a), b = m.byId.get(link.b);
        if (!shownAt(a, link.t) || !shownAt(b, link.t)) continue;
        const ya = Y(link.ya), yb = Y(link.yb);
        if ((ya < AXIS && yb < AXIS) || (ya > view.height && yb > view.height)) continue;
        let alpha;
        if (link.t > T) { if (!S.ghost) continue; alpha = 0.1; }
        else if (link.until <= T) alpha = 0.22;
        else alpha = hover && (hover === a || hover === b) ? 1 : 0.5;
        c.globalAlpha = alpha;
        c.strokeStyle = colours.link;
        c.fillStyle = colours.link;
        c.setLineDash(link.t <= T && link.until <= T ? [2, 3] : []);
        const bulge = Math.min(70, 12 + Math.abs(ya - yb) * 0.22);
        c.beginPath(); c.moveTo(x, ya); c.quadraticCurveTo(x + bulge, (ya + yb) / 2, x, yb); c.stroke();
        c.fillRect(x - 1.5, ya - 1.5, 3, 3);
        c.fillRect(x - 1.5, yb - 1.5, 3, 3);
      }
      c.setLineDash([]);
      c.globalAlpha = 1;
    }

    function drawLanes(c, v0, v1, T) {
      const colours = view.colours, margin = 30 / scale();
      for (const p of lanes) {
        if (p.lane0 > v1 + margin || p.lane1 < v0 - margin) continue;
        const y = Y(p.y);
        if (y < AXIS - 8 || y > view.height + 8) continue;
        for (const interval of p.shown) {
          const from = Math.max(interval[0], p.lane0), to = Math.min(interval[1], p.lane1);
          if (to <= from || to < v0 || from > v1) continue;
          const solidTo = Math.min(to, T);
          for (let i = 0; i < p.statuses.length && solidTo > from; i++) {
            const a = Math.max(p.statuses[i].t, from);
            const b = Math.min(i + 1 < p.statuses.length ? p.statuses[i + 1].t : Infinity, solidTo);
            if (b <= a || b < v0 || a > v1) continue;
            const xa = Math.round(Math.max(-2, X(a))), xb = Math.round(Math.min(view.width + 2, X(b)));
            c.fillStyle = statusColour(p, p.statuses[i].v);
            c.fillRect(xa, Math.round(y - BAR / 2), Math.max(1, xb - xa), BAR);
          }
          if (S.ghost && to > T) {
            const xa = Math.round(Math.max(-2, X(Math.max(from, T)))), xb = Math.round(Math.min(view.width + 2, X(to)));
            if (xb > xa) {
              c.globalAlpha = 0.35; c.fillStyle = colours.muted;
              c.fillRect(xa, Math.round(y), xb - xa, 1);
              c.globalAlpha = 1;
            }
          }
        }
        if (S.hover === p) {
          const xa = Math.round(Math.max(-2, X(p.lane0))), xb = Math.round(Math.min(view.width + 2, X(p.lane1)));
          c.strokeStyle = colours.text; c.lineWidth = 1;
          c.strokeRect(xa + 0.5, Math.round(y - BAR / 2 - 2) + 0.5, Math.max(1, xb - xa), BAR + 4);
        }
      }
    }

    function drawActivity(c, v0, v1, T) {
      const colours = view.colours, h = BAR / 2 + 2.5;
      const lastX = new Map();
      for (let i = firstAtOrAfter(acts, v0); i < acts.length && acts[i].t <= v1; i++) {
        const { act, p } = acts[i];
        if (!shownAt(p, act.t)) continue;
        const future = act.t > T;
        if (future && !S.ghost) continue;
        const x = Math.round(X(act.t)), y = Y(act.y);
        if (y < AXIS - 8 || y > view.height + 8) continue;
        if (x - (lastX.get(p) ?? -9) < 2) continue;
        lastX.set(p, x);
        if (future) {
          c.globalAlpha = 0.35; c.fillStyle = colours.muted; c.fillRect(x, y - 2, 1, 4); c.globalAlpha = 1;
        } else {
          c.fillStyle = colours[ACTIVITY_COLOURS[act.w]];
          c.fillRect(x, y - h, 1.5, h * 2);
        }
      }
    }

    function drawMark(c, mark, p, x, y) {
      const colours = view.colours;
      const named = SHAPES[p.type] !== undefined;
      switch (mark.k) {
        case 'created': {
          const r = named ? 4.2 : 3.2, shape = SHAPES[p.type] || 'square';
          c.fillStyle = colours.background; glyph(c, shape, x, y, r + 1.6);
          c.fillStyle = statusColour(p, mark.s); glyph(c, shape, x, y, r);
          break;
        }
        case 'status': {
          const r = mark.gate ? 3.4 : 2.4;
          c.fillStyle = colours.background; c.beginPath(); c.arc(x, y, r + 1.5, 0, 2 * Math.PI); c.fill();
          c.fillStyle = statusColour(p, mark.s); c.beginPath(); c.arc(x, y, r, 0, 2 * Math.PI); c.fill();
          if (mark.gate) { c.strokeStyle = colours.gate; c.lineWidth = 1.5; c.beginPath(); c.arc(x, y, r + 2, 0, 2 * Math.PI); c.stroke(); }
          break;
        }
        case 'ship': {
          const r = 4.6;
          c.fillStyle = colours.background; c.beginPath(); c.arc(x, y, r + 1.6, 0, 2 * Math.PI); c.fill();
          c.fillStyle = statusColour(p, mark.s); c.beginPath(); c.arc(x, y, r, 0, 2 * Math.PI); c.fill();
          if (mark.gate) { c.strokeStyle = colours.gate; c.lineWidth = 1.5; c.beginPath(); c.arc(x, y, r + 2, 0, 2 * Math.PI); c.stroke(); }
          if (statusClass(mark.s, m.types[p.type]) === 'done') {
            c.strokeStyle = colours.background; c.lineWidth = 1.4; c.beginPath();
            c.moveTo(x - r * 0.45, y); c.lineTo(x - r * 0.1, y + r * 0.38); c.lineTo(x + r * 0.5, y - r * 0.35); c.stroke();
          }
          break;
        }
        case 'archive': case 'delete': {
          const r = 3.2;
          c.strokeStyle = mark.k === 'delete' ? colours.warn : colours.archived; c.lineWidth = 1.6; c.beginPath();
          c.moveTo(x - r, y - r); c.lineTo(x + r, y + r); c.moveTo(x + r, y - r); c.lineTo(x - r, y + r); c.stroke();
          break;
        }
        case 'unarchive':
          c.strokeStyle = statusColour(p, statusAt(p, mark.t)); c.lineWidth = 1.5;
          c.beginPath(); c.arc(x, y, 3.2, 0, 2 * Math.PI); c.stroke();
          break;
        case 'move': c.strokeStyle = colours.link; c.lineWidth = 1.3; c.strokeRect(x - 2.5, y - 2.5, 5, 5); break;
        case 'rename': c.fillStyle = colours.muted; c.fillRect(x - 3, y - BAR / 2 - 4, 6, 1.5); break;
        default: break;
      }
    }

    function drawMarks(c, v0, v1, T) {
      const colours = view.colours, margin = 10 / scale();
      for (let i = firstAtOrAfter(marks, v0 - margin); i < marks.length && marks[i].t <= v1 + margin; i++) {
        const { mark, p } = marks[i];
        // An archive or delete cross caps the lane, so it shows when the page was shown just before it.
        const visible = mark.k === 'archive' || mark.k === 'delete' ? shownAt(p, mark.t - 1) : shownAt(p, mark.t);
        if (!visible) continue;
        const x = Math.round(X(mark.t)), y = Math.round(Y(mark.y));
        if (y < AXIS - 10 || y > view.height + 10) continue;
        if (mark.t > T) {
          if (!S.ghost) continue;
          c.globalAlpha = 0.5; c.fillStyle = colours.muted; c.fillRect(x - 1, y - 1, 2, 2); c.globalAlpha = 1;
          continue;
        }
        drawMark(c, mark, p, x, y);
      }
    }

    function drawLabels(c, v0, v1, T) {
      const colours = view.colours, lastEnd = new Map();
      c.textBaseline = 'middle';
      for (const p of lanes) {
        if (p.lane0 > T || p.lane0 > v1 || p.lane1 < v0 || !shownAt(p, p.lane0)) continue;
        const y = Y(p.y) - 7;
        if (y < AXIS || y > view.height) continue;
        const title = titleAt(p, T);
        if (!title) continue;
        const x = p.trunk ? Math.max(X(p.lane0) + 9, 8) : X(p.lane0) + 9;
        const available = (p.trunk ? view.width : Math.min(view.width, X(p.lane1) + 60)) - x;
        if (available < 70 || (lastEnd.get(p.track) ?? -Infinity) > x - 4) continue;
        c.font = p.trunk ? BOLD_FONT : FONT;
        let text = title, width = c.measureText(text).width;
        if (width > available - 4) {
          text = title.slice(0, Math.max(3, Math.floor((available - 10) / (width / title.length)))) + '…';
          width = c.measureText(text).width;
        }
        c.fillStyle = S.hover === p ? colours.text : colours.muted;
        c.fillText(text, x, y);
        lastEnd.set(p.track, x + width);
      }
    }

    function drawSettled(c, T) {
      const colours = view.colours, packed = new Map();
      settledHits = [];
      for (const p of settled) {
        if (p.finishT > T) break;
        if (!shownAt(p, p.finishT)) continue;
        // Glyphs that settle at one instant on one row are strung out side by side.
        let x = X(p.finishT) + BRANCH;
        const previous = packed.get(p.settleY);
        if (previous !== undefined && x < previous + 8) x = previous + 8;
        packed.set(p.settleY, x);
        const y = Y(p.settleY);
        if (x < -6 || x > view.width + 6 || y < AXIS - 6 || y > view.height + 6) continue;
        c.fillStyle = colours.background; c.beginPath(); c.arc(x, y, 3.6, 0, 2 * Math.PI); c.fill();
        c.fillStyle = statusColour(p, statusAt(p, T));
        glyph(c, SHAPES[p.type] || 'square', x, y, 2.6);
        settledHits.push({ p, x, y });
      }
    }

    function drawAxis(c, v0, v1, step, T) {
      const colours = view.colours, width = view.width;
      c.fillStyle = colours.background; c.fillRect(0, 0, width, AXIS);
      c.strokeStyle = colours.border; c.lineWidth = 1;
      c.beginPath(); c.moveTo(0, AXIS - 0.5); c.lineTo(width, AXIS - 0.5); c.stroke();
      c.font = FONT; c.textBaseline = 'middle'; c.fillStyle = colours.muted;
      for (let t = Math.ceil(v0 / step) * step; t < v1; t += step) {
        const x = Math.round(X(t));
        c.fillRect(x, AXIS - 5, 1, 5);
        c.fillText(step < DAY ? formatHour(t) : formatDay(t), x + 4, AXIS / 2);
      }
      for (const gap of m.gaps) {
        if (gap.t < v0 || gap.t > v1) continue;
        c.globalAlpha = gap.t > T ? 0.25 : 0.7;
        c.fillRect(Math.round(X(gap.t)), AXIS - 6, 1, 6);
        c.globalAlpha = 1;
      }
      if (m.recordingStart !== null && m.recordingStart >= v0 && m.recordingStart <= v1) {
        const x = Math.round(X(m.recordingStart));
        const label = 'recording started';
        const labelWidth = c.measureText(label).width + 8;
        c.fillStyle = colours.background; c.fillRect(x + 1, 1, labelWidth, AXIS - 7);
        c.fillStyle = colours.muted; c.fillRect(x, 0, 1, AXIS); c.fillText(label, x + 5, AXIS / 2);
      }
    }

    function drawPlayhead(c, T) {
      const colours = view.colours, x = Math.round(X(T));
      c.strokeStyle = colours.accent; c.lineWidth = 1;
      c.beginPath(); c.moveTo(x + 0.5, AXIS); c.lineTo(x + 0.5, view.height); c.stroke();
      c.font = BOLD_FONT; c.textBaseline = 'middle';
      const label = formatMoment(T), labelWidth = c.measureText(label).width + 12;
      c.fillStyle = colours.accent; c.fillRect(x - labelWidth / 2, 3, labelWidth, AXIS - 8);
      c.fillStyle = colours.background; c.fillText(label, x - labelWidth / 2 + 6, AXIS / 2 - 1);
    }

    function draw() {
      const c = stageContext, width = view.width, height = view.height, T = S.T;
      if (!width || !height) return;
      c.setTransform(view.dpr, 0, 0, view.dpr, 0, 0);
      c.globalAlpha = 1;
      c.fillStyle = view.colours.background;
      c.fillRect(0, 0, width, height);
      const v0 = S.x0, v1 = S.x0 + S.span;
      let step = GRID_STEPS[GRID_STEPS.length - 1];
      for (const candidate of GRID_STEPS) if (candidate * scale() >= 52) { step = candidate; break; }
      c.save();
      c.beginPath(); c.rect(0, AXIS, width, height - AXIS); c.clip();
      c.globalAlpha = 0.5; c.strokeStyle = view.colours.border; c.lineWidth = 1; c.beginPath();
      for (let t = Math.ceil(v0 / step) * step; t < v1; t += step) { const x = crisp(X(t)); c.moveTo(x, AXIS); c.lineTo(x, height); }
      c.stroke(); c.globalAlpha = 1;
      drawConnectors(c, v0, v1, T);
      drawLinks(c, T);
      drawLanes(c, v0, v1, T);
      drawActivity(c, v0, v1, T);
      drawMarks(c, v0, v1, T);
      drawLabels(c, v0, v1, T);
      drawSettled(c, T);
      if (m.recordingStart !== null) {
        const x = crisp(X(m.recordingStart));
        c.strokeStyle = view.colours.muted; c.lineWidth = 1;
        c.beginPath(); c.moveTo(x, AXIS); c.lineTo(x, height); c.stroke();
      }
      if (S.hover && S.hover.branchY !== null && !S.hover.trunk) {
        const x = crisp(X(S.hover.lane0));
        c.globalAlpha = 0.5; c.strokeStyle = view.colours.text; c.setLineDash([3, 3]);
        c.beginPath(); c.moveTo(x, Y(S.hover.branchY)); c.lineTo(x, Y(S.hover.y)); c.stroke();
        c.setLineDash([]); c.globalAlpha = 1;
      }
      c.restore();
      drawAxis(c, v0, v1, step, T);
      drawPlayhead(c, T);
    }

    function drawOverview() {
      const c = overviewContext, width = view.overviewWidth, height = view.overviewHeight, colours = view.colours;
      if (!width || !height) return;
      c.setTransform(view.dpr, 0, 0, view.dpr, 0, 0);
      c.fillStyle = colours.panel; c.fillRect(0, 0, width, height);
      const total = Math.max(1, t1 - t0);
      const xt = t => (t - t0) / total * width;
      const buckets = Math.max(1, Math.floor(width / 3));
      if (!overviewCache || overviewCache.buckets !== buckets) {
        const density = new Float32Array(buckets), shownCount = new Float32Array(buckets);
        for (const t of m.eventTs) density[Math.min(buckets - 1, Math.floor((t - t0) / total * buckets))]++;
        for (let i = 0; i < buckets; i++) {
          const t = t0 + (i + 0.5) / buckets * total;
          for (const p of m.pages) if (shownAt(p, t)) shownCount[i]++;
        }
        overviewCache = { buckets, density, shownCount,
          maxDensity: Math.max(1, ...density), maxShown: Math.max(1, ...shownCount) };
      }
      const cache = overviewCache, bucketWidth = width / buckets;
      c.fillStyle = colours.border;
      for (let i = 0; i < buckets; i++) {
        const h = cache.density[i] / cache.maxDensity * (height - 14);
        if (h > 0) c.fillRect(i * bucketWidth, height - h, Math.max(1, bucketWidth - 0.5), h);
      }
      c.strokeStyle = colours.muted; c.lineWidth = 1; c.beginPath();
      for (let i = 0; i < buckets; i++) {
        const y = height - 2 - cache.shownCount[i] / cache.maxShown * (height - 16);
        if (i) c.lineTo(i * bucketWidth + bucketWidth / 2, y); else c.moveTo(bucketWidth / 2, y);
      }
      c.stroke();
      c.fillStyle = colours.muted;
      for (const gap of m.gaps) c.fillRect(Math.round(xt(gap.t)), 0, 1, 4);
      if (m.recordingStart !== null) c.fillRect(Math.round(xt(m.recordingStart)), 0, 1, height);
      c.globalAlpha = 0.5; c.strokeStyle = colours.text;
      c.strokeRect(crisp(xt(S.x0)), 1.5, Math.max(2, S.span / total * width), height - 3);
      c.globalAlpha = 1;
      c.fillStyle = colours.accent; c.fillRect(Math.round(xt(S.T)), 0, 2, height);
      c.fillStyle = colours.muted; c.font = SMALL_FONT; c.textBaseline = 'top';
      c.fillText(formatDay(t0), 4, 3);
      const last = formatDay(t1);
      c.fillText(last, width - c.measureText(last).width - 4, 3);
    }

    // The vertical camera eases towards the rows touched in the last three days.
    function camera(dtSeconds) {
      if (!S.follow) return;
      S.x0 = S.T - FOLLOW_AT * S.span;
      const visible = view.height - AXIS;
      let target;
      if (layout.height <= visible) target = (layout.height - visible) / 2;
      else {
        const from = firstAtOrAfter(touches, S.T - 3 * DAY), to = firstAtOrAfter(touches, S.T + 1);
        if (to <= from) target = S.y0;
        else {
          const stride = Math.max(1, Math.floor((to - from) / 60));
          let sum = 0, n = 0;
          for (let i = from; i < to; i += stride) { sum += touches[i].y; n++; }
          target = Math.max(-40, Math.min(layout.height - visible + 40, sum / n - visible / 2));
        }
      }
      const previous = S.y0;
      S.y0 = S.cameraSet ? S.y0 + (target - S.y0) * (1 - Math.exp(-3 * dtSeconds)) : target;
      S.cameraSet = true;
      if (Math.abs(S.y0 - previous) > 0.05) S.dirty = true;
    }

    return { S, view, size, recolour, draw, drawOverview, camera, X, Y, settledHits: () => settledHits, lanes };
  }

  function drawMessage(stage, text) {
    const box = stage.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
    if (!box.width || !box.height) return;
    stage.width = Math.round(box.width * dpr); stage.height = Math.round(box.height * dpr);
    const c = stage.getContext('2d'), colours = readColours();
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.fillStyle = colours.background; c.fillRect(0, 0, box.width, box.height);
    c.fillStyle = colours.muted; c.font = FONT; c.textAlign = 'center'; c.textBaseline = 'middle';
    c.fillText(text, box.width / 2, box.height / 2);
    c.textAlign = 'start';
  }

  function showMessage(root, text) {
    const stage = root.querySelector('#tl-stage');
    const redraw = () => drawMessage(stage, text);
    redraw();
    if (typeof ResizeObserver !== 'undefined') new ResizeObserver(redraw).observe(stage);
    new MutationObserver(redraw).observe(document.body, { attributes: true, attributeFilter: ['class'] });
  }

  function mount(root) {
    fetch(root.dataset.src, { cache: 'no-store' })
      .then(response => {
        if (!response.ok) throw new Error(String(response.status));
        return response.json();
      })
      .then(data => {
        if (data.t0 === null || data.t1 === null) { showMessage(root, 'No history recorded yet for this workspace.'); return; }
        const m = fold(data);
        const viewer = createViewer(root, m, layoutMetro(m));
        start(root, m, viewer);
      })
      .catch(error => showMessage(root, 'Could not load the timeline (' + error.message + ').'));
  }

  const SPEEDS = [0.25, 1, 4, 16];
  const MIN_SPAN = 1.5 * DAY, MAX_SPAN = 400 * DAY;
  const CHIP_LABELS = { idle: 'not started', active: 'in progress', review: 'in review', done: 'finished', warn: 'blocked' };

  function start(root, m, viewer) {
    const { S, view } = viewer;
    const t0 = m.t0, t1 = m.t1;
    const stage = root.querySelector('#tl-stage'), overview = root.querySelector('#tl-overview');
    const tip = root.querySelector('#tl-tip'), chips = root.querySelector('#tl-chips');
    const playButton = root.querySelector('#tl-play'), followButton = root.querySelector('#tl-follow');
    const futureButton = root.querySelector('#tl-future');
    const speedButtons = Array.from(root.querySelectorAll('[data-speed]'));
    let pointer = null, drag = null, scrubbing = false;

    function setPlaying(playing) {
      S.playing = playing;
      playButton.textContent = playing ? 'Pause' : 'Play';
      S.dirty = true;
    }
    function setSpeed(speed) {
      S.speed = speed;
      for (const button of speedButtons) button.classList.toggle('on', Number(button.dataset.speed) === speed);
    }
    function setFollow(follow) { S.follow = follow; followButton.classList.toggle('on', follow); S.dirty = true; }
    function setGhost(ghost) { S.ghost = ghost; futureButton.classList.toggle('on', ghost); S.dirty = true; }
    function seek(t) {
      S.T = Math.max(t0, Math.min(t1, t));
      if (S.follow) S.x0 = S.T - FOLLOW_AT * S.span;
      S.dirty = true;
    }
    function togglePlay() {
      if (!S.playing && S.T >= t1) seek(t0);
      setPlaying(!S.playing);
    }
    function nextEventAfter(T) {
      const ts = m.eventTs;
      let lo = 0, hi = ts.length;
      while (lo < hi) { const mid = (lo + hi) >> 1; if (ts[mid] <= T) lo = mid + 1; else hi = mid; }
      return lo < ts.length ? ts[lo] : null;
    }

    function updateChips() {
      const counts = { idle: 0, active: 0, review: 0, done: 0, warn: 0 };
      let shown = 0;
      for (const p of m.pages) {
        if (!shownAt(p, S.T)) continue;
        shown++;
        counts[statusClass(statusAt(p, S.T), m.types[p.type])]++;
      }
      chips.innerHTML = '<b>' + shown + '</b> shown' + Object.keys(counts).map(name =>
        '<span class="tl-chip"><i class="tl-' + name + '"></i>' + counts[name] + ' ' + CHIP_LABELS[name] + '</span>').join('');
    }

    function hit(mx, my) {
      const tp = S.x0 + mx / view.width * S.span;
      let best = null, bestDistance = 9;
      for (const p of viewer.lanes) {
        const distance = Math.abs(my - viewer.Y(p.y));
        if (distance >= bestDistance) continue;
        if (mx < viewer.X(p.lane0) - 6 || mx > viewer.X(p.lane1) + 6) continue;
        const t = Math.max(p.lane0, Math.min(p.lane1, tp));
        if (t > S.T && !S.ghost) continue;
        if (!shownAt(p, t) && !shownAt(p, t - 1)) continue;
        best = p; bestDistance = distance;
      }
      for (const glyphHit of viewer.settledHits()) {
        const distance = Math.hypot(mx - glyphHit.x, my - glyphHit.y);
        if (distance < Math.min(bestDistance, 7)) { best = glyphHit.p; bestDistance = distance; }
      }
      return best ? { p: best, t: tp } : null;
    }

    function tipLine(text, className) {
      const line = document.createElement('div');
      if (className) line.className = className;
      line.textContent = text;
      return line;
    }
    function statusLine(label, p, t) {
      const line = document.createElement('div');
      const status = statusAt(p, t);
      line.append(label + ': ');
      if (status !== null) {
        const dot = document.createElement('i');
        dot.className = 'tl-' + statusClass(status, m.types[p.type]);
        line.append(dot, status);
      } else line.append('not created yet');
      return line;
    }
    function updateTip() {
      if (!pointer || drag) { tip.style.display = 'none'; return; }
      const found = hit(pointer.x, pointer.y);
      const hovered = found ? found.p : null;
      if (hovered !== S.hover) { S.hover = hovered; S.dirty = true; }
      if (!found) { tip.style.display = 'none'; return; }
      const p = found.p, tp = found.t, T = S.T;
      const title = document.createElement('b');
      title.textContent = titleAt(p, T) ?? titleAt(p, tp) ?? titleAt(p, p.born);
      tip.replaceChildren(title, tipLine(p.type, 'tl-muted'), statusLine('at playhead (' + formatMoment(T) + ')', p, T));
      if (Math.abs(tp - T) > HOUR) tip.append(statusLine('at pointer (' + formatMoment(tp) + ')', p, tp));
      tip.append(tipLine(p.present ? 'present when recording started ' + formatDay(p.born) : 'created ' + formatDay(p.born), 'tl-muted'));
      const end = lastShownEnd(p);
      if (end < t1) {
        const ended = p.deleted && p.endedAt === end ? 'deleted ' : p.endedAt === end ? 'gone when recording started ' : 'archived ';
        tip.append(tipLine(ended + formatDay(end), 'tl-muted'));
      }
      if (m.recordingStart !== null && (T < m.recordingStart || tp < m.recordingStart)) tip.append(tipLine('from PR history', 'tl-muted'));
      tip.style.display = 'block';
      tip.style.left = Math.max(0, Math.min(view.width - tip.offsetWidth - 4, pointer.x + 14)) + 'px';
      tip.style.top = Math.max(0, Math.min(view.height - tip.offsetHeight - 4, pointer.y + 14)) + 'px';
    }

    // A clicked button gives focus back, so Space keeps meaning play and pause rather than pressing it again.
    function onClick(button, action) {
      button.addEventListener('click', event => { action(); event.currentTarget.blur(); });
    }
    onClick(playButton, togglePlay);
    for (const button of speedButtons) onClick(button, () => setSpeed(Number(button.dataset.speed)));
    onClick(followButton, () => setFollow(!S.follow));
    onClick(futureButton, () => setGhost(!S.ghost));
    window.addEventListener('keydown', event => {
      if (event.ctrlKey || event.metaKey || event.altKey) return;
      if (event.target && /^(INPUT|TEXTAREA|SELECT)$/.test(event.target.tagName)) return;
      if (event.code === 'Space') { event.preventDefault(); togglePlay(); }
      else if (event.key >= '1' && event.key <= '4') setSpeed(SPEEDS[Number(event.key) - 1]);
      else if (event.key === 'f' || event.key === 'F') setFollow(!S.follow);
      else if (event.key === 'g' || event.key === 'G') setGhost(!S.ghost);
      else if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
        event.preventDefault();
        seek(S.T + (event.key === 'ArrowRight' ? 1 : -1) * (event.shiftKey ? 7 : 1) * DAY);
      }
    });
    stage.addEventListener('wheel', event => {
      event.preventDefault();
      const box = stage.getBoundingClientRect();
      const anchor = S.follow ? FOLLOW_AT * view.width : event.clientX - box.left;
      const at = S.x0 + anchor / view.width * S.span;
      S.span = Math.max(MIN_SPAN, Math.min(MAX_SPAN, S.span * (event.deltaY < 0 ? 1 / 1.15 : 1.15)));
      S.x0 = at - anchor / view.width * S.span;
      S.dirty = true;
    }, { passive: false });
    stage.addEventListener('pointerdown', event => {
      drag = { x: event.clientX, y: event.clientY, x0: S.x0, y0: S.y0, moved: false };
      stage.setPointerCapture(event.pointerId);
    });
    stage.addEventListener('pointermove', event => {
      const box = stage.getBoundingClientRect();
      pointer = { x: event.clientX - box.left, y: event.clientY - box.top };
      if (drag) {
        const dx = event.clientX - drag.x, dy = event.clientY - drag.y;
        if (drag.moved || Math.abs(dx) + Math.abs(dy) > 3) {
          drag.moved = true;
          if (S.follow) setFollow(false);
          S.x0 = drag.x0 - dx / view.width * S.span;
          S.y0 = drag.y0 - dy;
          S.dirty = true;
        }
      }
      updateTip();
    });
    const endDrag = () => { drag = null; updateTip(); };
    stage.addEventListener('pointerup', endDrag);
    stage.addEventListener('pointercancel', endDrag);
    stage.addEventListener('pointerleave', () => {
      pointer = null; tip.style.display = 'none';
      if (S.hover) { S.hover = null; S.dirty = true; }
    });
    function scrubTo(event) {
      const box = overview.getBoundingClientRect();
      seek(t0 + (event.clientX - box.left) / box.width * (t1 - t0));
    }
    overview.addEventListener('pointerdown', event => { scrubbing = true; overview.setPointerCapture(event.pointerId); scrubTo(event); });
    overview.addEventListener('pointermove', event => { if (scrubbing) scrubTo(event); });
    overview.addEventListener('pointerup', () => { scrubbing = false; });
    overview.addEventListener('pointercancel', () => { scrubbing = false; });

    if (typeof ResizeObserver !== 'undefined') new ResizeObserver(() => viewer.size()).observe(stage);
    window.addEventListener('resize', () => viewer.size());
    new MutationObserver(() => viewer.recolour()).observe(document.body, { attributes: true, attributeFilter: ['class'] });
    const sheet = document.getElementById('js-stylesheet');
    if (sheet) sheet.addEventListener('load', () => viewer.recolour());

    setSpeed(0.25);
    setFollow(true);
    setGhost(true);
    seek(t0);
    setPlaying(true);
    viewer.size();
    let last = performance.now(), drawnFrames = 0;
    function frame(now) {
      const dtSeconds = Math.min(0.1, (now - last) / 1000);
      last = now;
      if (S.playing) {
        S.T = playheadStep(S.T, dtSeconds, S.speed, nextEventAfter(S.T));
        if (S.T >= t1) { S.T = t1; setPlaying(false); }
        S.dirty = true;
      }
      viewer.camera(dtSeconds);
      if (S.dirty) {
        S.dirty = false;
        viewer.draw();
        viewer.drawOverview();
        if (!S.playing || ++drawnFrames % 6 === 0) updateChips();
        if (pointer && S.playing) updateTip();
      }
      requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }

  const PastaTimeline = { statusClass, playheadStep, fold, isShown, statusAt, titleAt, parentAt, layoutMetro, mount };
  root.PastaTimeline = PastaTimeline;
  if (typeof module !== 'undefined' && module.exports) module.exports = PastaTimeline;
})(typeof globalThis !== 'undefined' ? globalThis : this);
