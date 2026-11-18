// Dependency-free check of the timeline renderer's pure functions.
// Run: node tests/timeline/check_timeline.js [--types <file>]
// --types replaces the embedded page-type table with one written from lifecycle_log.timeline_types().
'use strict';
const fs = require('fs');
const path = require('path');
const TL = require('../../src/static/timeline/timeline.js');

const DAY = 86400000, HOUR = 3600000;

// The production table for the types the fixtures use, as lifecycle_log.timeline_types() serves it.
let TYPES = {
  'agent-plan': { initial: 'draft', finish: ['accepted'], elements: {}, gates: [] },
  'bug-report': { initial: 'draft', finish: ['closed'], elements: {}, gates: [['done', 'closed']] },
  epic: { initial: 'draft', finish: ['shipped', 'abandoned'], elements: { 'questions.items': 'Question' },
    gates: [['decomposition', 'abandoned'], ['draft', 'abandoned'], ['executing', 'abandoned'], ['grounding', 'abandoned'],
      ['planReview', 'abandoned'], ['review', 'abandoned'], ['review', 'shipped']] },
  'feature-brief': { initial: 'draft', finish: ['shipped', 'abandoned'], elements: { 'questions.items': 'Question' },
    gates: [['building', 'abandoned'], ['done', 'shipped'], ['draft', 'abandoned'], ['grounding', 'abandoned'],
      ['planReview', 'abandoned'], ['planning', 'abandoned'], ['review', 'abandoned'], ['spec', 'abandoned']] },
  'implementation-plan': { initial: 'draft', finish: ['ready'], elements: { 'steps.items': 'Step' }, gates: [] },
  'simple-change': { initial: 'draft', finish: ['closed'], elements: {}, gates: [['done', 'closed']] },
  'testing-plan': { initial: 'draft', finish: ['ready'], elements: { 'cases.items': 'Case' }, gates: [] },
  toc: { initial: 'active', finish: [], elements: {}, gates: [] },
};
const typesArg = process.argv.indexOf('--types');
if (typesArg > 0) TYPES = JSON.parse(fs.readFileSync(process.argv[typesArg + 1], 'utf8'));

let failures = 0;
function ok(condition, message) {
  if (!condition) { failures++; console.log('FAIL ' + message); }
}

// --- statusClass ---------------------------------------------------------------
ok(TL.statusClass('accepted', TYPES['agent-plan']) === 'done', 'agent-plan accepted is done');
ok(TL.statusClass('ready', TYPES['agent-plan']) === 'active', 'agent-plan ready is active');
ok(TL.statusClass('abandoned', TYPES['feature-brief']) === 'warn', 'abandoned is warn before done');
ok(TL.statusClass('planReview', TYPES['feature-brief']) === 'review', 'planReview is review');
ok(TL.statusClass('judging', TYPES['feature-brief']) === 'review', 'judging is review');
ok(TL.statusClass('draft', TYPES['feature-brief']) === 'idle', 'the initial status is idle');
ok(TL.statusClass('building', TYPES['feature-brief']) === 'active', 'another status is active');
ok(TL.statusClass('ready', TYPES['implementation-plan']) === 'done', 'a plan finishes at ready');
ok(TL.statusClass('draft', undefined) === 'active', 'a type missing from the table has no initial status');
ok(TL.statusClass('blocked', undefined) === 'warn', 'warn names need no type');

// --- playheadStep --------------------------------------------------------------
{
  const T = 1790000000000;
  ok(TL.playheadStep(T, 1, 0.25, T + HOUR) === T + 21600000, 'a near event plays at speed');
  ok(TL.playheadStep(T, 1, 0.25, T + 7 * HOUR) === T + 129600000, 'a far event plays six times faster');
  ok(TL.playheadStep(T, 1, 0.25, T + 6 * HOUR) === T + 21600000, 'exactly six hours ahead is not far');
  ok(TL.playheadStep(T, 1, 0.25, null) === T + 21600000, 'no next event plays at speed');
}

// --- fixtures -------------------------------------------------------------------
// Events are written without seq; numbered() stamps seq 1..N in order, a gap taking up its missing seqs.
function numbered(events) {
  let seq = 1;
  return events.map(event => {
    const line = Object.assign({ seq }, event);
    seq += event.kind === 'gap' ? event.missing : 1;
    return line;
  });
}
function payload(events) {
  return { workspace: { id: 'ws:check', name: 'check' }, t0: events.length ? events[0].ts : null,
    t1: events.length ? events[events.length - 1].ts : null, types: TYPES, events };
}
const created = (ts, page, type, title, parent, status) => ({ ts, page, kind: 'created', type, title, parent, status });
const present = (ts, page, type, title, parent, status, archived, links) =>
  ({ ts, page, kind: 'present', type, title, parent, status, archived: !!archived, links: links || [] });
const statusMove = (ts, page, from, to) => ({ ts, page, kind: 'status', from, to });

// Fixture B: one event of every kind, the archive edge cases and a baseline.
const B0 = Date.UTC(2026, 9, 1, 8);
const at = hours => B0 + hours * HOUR;
const B_R = at(20);
const FIXTURE_B = numbered([
  created(at(0), 'toc:t1', 'toc', 'Features', null, 'active'),
  created(at(0.5), 'feature-brief:f1', 'feature-brief', 'F1', 'toc:t1', 'draft'),
  created(at(0.5), 'implementation-plan:ip1', 'implementation-plan', 'F1 plan', 'feature-brief:f1', 'draft'),
  created(at(0.5), 'testing-plan:tp1', 'testing-plan', 'F1 tests', 'feature-brief:f1', 'draft'),
  statusMove(at(1), 'feature-brief:f1', 'draft', 'grounding'),
  created(at(1), 'epic:e1', 'epic', 'E1', 'toc:t1', 'draft'),
  { ts: at(1.2), page: 'feature-brief:f1', kind: 'el_added', section: 'questions', field: 'items', el: 'q1', status: 'open' },
  { ts: at(1.4), page: 'feature-brief:f1', kind: 'el_status', section: 'questions', field: 'items', el: 'q1', from: 'open', to: 'answered' },
  created(at(1.5), 'feature-brief:c1', 'feature-brief', 'C1', 'epic:e1', 'draft'),
  created(at(1.5), 'feature-brief:c2', 'feature-brief', 'C2', 'epic:e1', 'draft'),
  statusMove(at(2), 'implementation-plan:ip1', 'draft', 'ready'),
  statusMove(at(2), 'testing-plan:tp1', 'draft', 'ready'),
  created(at(2), 'feature-brief:d1', 'feature-brief', 'D1', 'toc:t1', 'draft'),
  statusMove(at(3), 'feature-brief:f1', 'grounding', 'building'),
  created(at(3), 'feature-brief:old1', 'feature-brief', 'Old', 'toc:t1', 'draft'),
  { ts: at(4), page: 'implementation-plan:ip1', kind: 'el_status', section: 'steps', field: 'items', el: 's1', from: 'todo', to: 'done' },
  { ts: at(5), page: 'testing-plan:tp1', kind: 'el_status', section: 'cases', field: 'items', el: 'k1', from: 'pending', to: 'passed' },
  { ts: at(5), page: 'feature-brief:f1', kind: 'edited', section: 'summary', field: 'body' },
  { ts: at(5), page: 'feature-brief:f1', kind: 'el_edited', section: 'components', field: 'items', el: 'x1' },
  statusMove(at(6), 'feature-brief:f1', 'building', 'done'),
  statusMove(at(7), 'feature-brief:f1', 'done', 'shipped'),
  { ts: at(8), page: 'epic:e1', kind: 'archived' },
  { ts: at(9), page: 'feature-brief:c2', kind: 'moved', from_parent: 'epic:e1', to_parent: 'toc:t1' },
  { ts: at(10), page: 'epic:e1', kind: 'unarchived' },
  { ts: at(11), page: 'feature-brief:f1', kind: 'renamed', from: 'F1', title: 'F1 renamed' },
  { ts: at(12), page: 'feature-brief:f1', kind: 'linked', to: 'epic:e1', role: 'relates-to' },
  { ts: at(13), page: 'feature-brief:f1', kind: 'unlinked', to: 'epic:e1', role: 'relates-to' },
  { ts: at(14), page: 'feature-brief:d1', kind: 'deleted', type: 'feature-brief', title: 'D1', status: 'draft' },
  { ts: at(15), page: 'feature-brief:f1', kind: 'teleported' },
  statusMove(at(16), 'feature-brief:ghost', 'draft', 'building'),
  { ts: at(17), page: 'feature-brief:f1', kind: 'el_removed', section: 'components', field: 'items', el: 'x1' },
  // the baseline: old1 is not named, e2 is archived and h1 sits under it
  present(B_R, 'toc:t1', 'toc', 'Features', null, 'active'),
  present(B_R, 'feature-brief:f1', 'feature-brief', 'F1 renamed', 'toc:t1', 'shipped'),
  present(B_R, 'implementation-plan:ip1', 'implementation-plan', 'F1 plan', 'feature-brief:f1', 'ready'),
  present(B_R, 'testing-plan:tp1', 'testing-plan', 'F1 tests', 'feature-brief:f1', 'ready'),
  present(B_R, 'epic:e1', 'epic', 'E1', 'toc:t1', 'draft', false, [{ to: 'feature-brief:c1', role: 'tracks' }]),
  present(B_R, 'feature-brief:c1', 'feature-brief', 'C1', 'epic:e1', 'draft'),
  present(B_R, 'feature-brief:c2', 'feature-brief', 'C2', 'toc:t1', 'draft'),
  present(B_R, 'epic:e2', 'epic', 'E2', 'toc:t1', 'draft', true),
  present(B_R, 'feature-brief:h1', 'feature-brief', 'Hidden', 'epic:e2', 'draft'),
  created(at(21), 'feature-brief:n1', 'feature-brief', 'New', 'toc:t1', 'draft'),
  { ts: at(22), page: null, kind: 'gap', missing: 2 },
  statusMove(at(22), 'feature-brief:n1', 'draft', 'grounding'),
]);

// --- fold: every kind becomes its mark, link or tick ------------------------------
{
  const m = TL.fold(payload(FIXTURE_B));
  const get = id => m.byId.get(id);
  const f1 = get('feature-brief:f1');
  const marksOf = (p, k) => p.marks.filter(mark => mark.k === k);
  ok(m.pages.length === 12, 'fixture B folds 12 pages, got ' + m.pages.length);
  ok(!m.byId.has('feature-brief:ghost'), 'an event for an unknown page creates nothing');
  ok(marksOf(f1, 'created').length === 1 && marksOf(f1, 'created')[0].t === at(0.5), 'created mark at creation');
  ok(marksOf(f1, 'status').length === 3, 'one status mark per non-finish move, got ' + marksOf(f1, 'status').length);
  ok(marksOf(f1, 'ship').length === 1 && f1.finishT === at(7) && marksOf(f1, 'ship')[0].t === at(7), 'one ship mark at the first finish move');
  ok(marksOf(f1, 'ship')[0].gate === true, 'the human-gated finish move is a gate');
  ok(marksOf(f1, 'status').every(mark => mark.gate === false), 'agent moves are not gates');
  ok(marksOf(f1, 'rename').length === 1, 'rename mark');
  ok(marksOf(get('feature-brief:c2'), 'move').length === 1, 'move mark');
  ok(marksOf(get('epic:e1'), 'archive').length === 1 && marksOf(get('epic:e1'), 'unarchive').length === 1, 'archive and unarchive marks');
  ok(marksOf(get('feature-brief:d1'), 'delete').length === 1 && get('feature-brief:d1').endedAt === at(14), 'delete mark ends the page');
  const acts = f1.acts.map(a => a.w).join(',');
  ok(acts === 'asked,answered,edit,edit,edit', 'feature acts asked, answered and edits, got ' + acts);
  ok(get('implementation-plan:ip1').acts.length === 1 && get('implementation-plan:ip1').acts[0].w === 'step', 'step done');
  ok(get('testing-plan:tp1').acts.length === 1 && get('testing-plan:tp1').acts[0].w === 'case', 'case passed');
  const f1Links = m.links.filter(link => link.a === 'feature-brief:f1');
  ok(f1Links.length === 1 && f1Links[0].t === at(12) && f1Links[0].until === at(13), 'a link lives from linked to unlinked');
  ok(m.links.some(link => link.a === 'epic:e1' && link.b === 'feature-brief:c1' && link.t === B_R && link.until === Infinity),
    'a baseline link starts at recording start');
  ok(m.gaps.length === 1 && m.gaps[0].missing === 2, 'one gap');
  ok(m.recordingStart === B_R, 'recording starts at the present events');
  ok(TL.titleAt(f1, at(10.9)) === 'F1' && TL.titleAt(f1, at(11)) === 'F1 renamed', 'titleAt across a rename');
  ok(TL.titleAt(f1, at(0.4)) === null && TL.statusAt(f1, at(0.4)) === null, 'nothing before born');
  ok(TL.statusAt(f1, at(6.5)) === 'done' && TL.statusAt(f1, at(7)) === 'shipped', 'statusAt across a move');
  const c1 = get('feature-brief:c1'), c2 = get('feature-brief:c2');
  ok(TL.isShown(m, c1, at(7.9)) && !TL.isShown(m, c1, at(8)) && TL.isShown(m, c1, at(10)), 'a child hides while its parent is archived');
  ok(!TL.isShown(m, c2, at(8.5)) && TL.isShown(m, c2, at(9)), 'a child moved out from under an archived parent shows again');
  ok(!TL.isShown(m, get('feature-brief:d1'), at(14)) && TL.isShown(m, get('feature-brief:d1'), at(13.9)), 'a deleted page is gone');
  ok(get('feature-brief:old1').endedAt === B_R, 'a page the baseline does not name ends at recording start');
  ok(get('feature-brief:n1').endedAt === null, 'a page created after the baseline does not end');
  ok(get('feature-brief:h1').present && get('feature-brief:h1').born === B_R && !TL.isShown(m, get('feature-brief:h1'), B_R),
    'a page present under an archived parent is hidden');
  ok(marksOf(get('feature-brief:h1'), 'created').length === 0, 'a present page has no created mark');
  ok(f1.marks.every(mark => mark.t !== B_R), 'a resync draws no mark');
  ok(get('implementation-plan:ip1').finishT === at(2), 'a plan finishes at ready');
}

// --- fixture A: the committed back-fill, a synthetic baseline and a recorded tail ----------
const BACKFILL = fs.readFileSync(path.join(__dirname, '..', '..', 'backfill', 'ws_mrteq0c5-238cf6.jsonl'), 'utf8')
  .split('\n').map(line => line.replace(/\r$/, '')).filter(Boolean).map(line => JSON.parse(line));
const FEATURES = 'toc:ms90fb2w-721ea1', BUGS = 'toc:ms90fbg0-ba90c1';
const RENAMED = 'simple-change:mt8gqcd2-2065c2', REOPENED = 'feature-brief:mtiml5v4-6c209f';
const ARCHIVED = 'feature-brief:mt91nm1k-10abf0', MOVED = 'simple-change:mt914isl-8ecfc4';
const A_R = BACKFILL[BACKFILL.length - 1].ts + DAY;
const atR = hours => A_R + hours * HOUR;
const FIXTURE_A = BACKFILL.concat(numbered([
  present(A_R, FEATURES, 'toc', 'Features', null, 'active'),
  present(A_R, BUGS, 'toc', 'Bug Reports', null, 'active'),
  present(A_R, 'toc:docs', 'toc', 'Documentation', null, 'active'),
  present(A_R, RENAMED, 'simple-change', 'Drop the block set (as recorded)', FEATURES, 'closed'),
  present(A_R, REOPENED, 'feature-brief', 'Stage-entry commands', FEATURES, 'building'),
  present(A_R, 'implementation-plan:mtiml5v5-6eeb03', 'implementation-plan', 'plan', REOPENED, 'ready'),
  present(A_R, 'testing-plan:mtiml5v5-87add0', 'testing-plan', 'tests', REOPENED, 'ready'),
  present(A_R, ARCHIVED, 'feature-brief', 'Block-arg helpers', FEATURES, 'shipped', true),
  present(A_R, MOVED, 'simple-change', 'Idempotent initial sections', BUGS, 'closed'),
  present(A_R, 'feature-brief:new-live', 'feature-brief', 'Live work', FEATURES, 'building', false,
    [{ to: REOPENED, role: 'relates-to' }]),
  present(A_R, 'feature-brief:new-done', 'feature-brief', 'Done work', FEATURES, 'shipped'),
  present(A_R, 'epic:new-epic', 'epic', 'Shelved epic', 'toc:docs', 'executing', true),
  present(A_R, 'feature-brief:new-under', 'feature-brief', 'Under the shelved epic', 'epic:new-epic', 'draft'),
  created(atR(1), 'feature-brief:tail1', 'feature-brief', 'Recorded feature', FEATURES, 'draft'),
  created(atR(1), 'implementation-plan:tail1-plan', 'implementation-plan', 'Recorded plan', 'feature-brief:tail1', 'draft'),
  statusMove(atR(2), 'feature-brief:tail1', 'draft', 'grounding'),
  statusMove(atR(3), 'feature-brief:tail1', 'grounding', 'building'),
  statusMove(atR(4), 'implementation-plan:tail1-plan', 'draft', 'ready'),
  { ts: atR(5), page: 'implementation-plan:tail1-plan', kind: 'el_status', section: 'steps', field: 'items', el: 's1', from: 'todo', to: 'done' },
  { ts: atR(6), page: 'feature-brief:tail1', kind: 'renamed', from: 'Recorded feature', title: 'Recorded feature, renamed' },
  { ts: atR(7), page: 'feature-brief:new-live', kind: 'archived' },
  { ts: atR(9), page: 'feature-brief:new-live', kind: 'unarchived' },
  { ts: atR(10), page: 'feature-brief:new-under', kind: 'moved', from_parent: 'epic:new-epic', to_parent: FEATURES },
  { ts: atR(11), page: MOVED, kind: 'deleted', type: 'simple-change', title: 'Idempotent initial sections', status: 'closed' },
  { ts: atR(12), page: 'epic:new-epic', kind: 'unarchived' },
  statusMove(atR(13), 'feature-brief:tail1', 'building', 'done'),
  statusMove(atR(14), 'feature-brief:tail1', 'done', 'shipped'),
]).map(line => Object.assign(line, { seq: line.seq + BACKFILL.length })));

// --- brute force: replay the events up to T, sharing nothing with the fold ------------------
function bruteForce(events, T) {
  const state = new Map();
  const namedByBaseline = new Set(events.filter(e => e.kind === 'present').map(e => e.page));
  let baselineSeen = false;
  for (const e of events) {
    if (e.ts > T) break;
    if (e.kind === 'present') {
      if (!baselineSeen) {
        baselineSeen = true;
        for (const [id, page] of state) if (!namedByBaseline.has(id)) page.gone = true;
      }
      const page = state.get(e.page);
      if (!page) state.set(e.page, { title: e.title, parent: e.parent, status: e.status, archived: e.archived, gone: false, deleted: false });
      else if (!page.deleted) Object.assign(page, { title: e.title, parent: e.parent, status: e.status, archived: e.archived });
      continue;
    }
    if (e.kind === 'created') {
      if (!state.has(e.page)) state.set(e.page, { title: e.title, parent: e.parent, status: e.status, archived: false, gone: false, deleted: false });
      continue;
    }
    const page = state.get(e.page);
    if (!page || page.deleted) continue;
    if (e.kind === 'status') page.status = e.to;
    else if (e.kind === 'renamed') page.title = e.title;
    else if (e.kind === 'moved') page.parent = e.to_parent;
    else if (e.kind === 'archived') page.archived = true;
    else if (e.kind === 'unarchived') page.archived = false;
    else if (e.kind === 'deleted') { page.gone = true; page.deleted = true; }
  }
  function shown(id) {
    const page = state.get(id);
    if (!page || page.gone) return false;
    let q = page;
    for (let depth = 0; q && depth < 64; depth++) {
      if (q.archived) return false;
      q = q.parent === null ? null : state.get(q.parent);
    }
    return true;
  }
  return { state, shown };
}

function sampleMoments(events, seed) {
  const t0 = events[0].ts, t1 = events[events.length - 1].ts;
  let s = seed >>> 0;
  const random = () => (s = (s * 1664525 + 1013904223) >>> 0) / 4294967296;
  const moments = [];
  for (let i = 0; i < 500; i++) moments.push(Math.floor(t0 - DAY + random() * (t1 - t0 + 2 * DAY)));
  for (const ts of new Set(events.map(e => e.ts))) moments.push(ts, ts - 1);
  return moments.sort((a, b) => a - b);
}

function compareWithBruteForce(name, events) {
  const m = TL.fold(payload(events));
  let mismatches = 0;
  for (const T of sampleMoments(events, 7)) {
    const brute = bruteForce(events, T);
    for (const p of m.pages) {
      const expected = brute.state.get(p.id);
      const shown = brute.shown(p.id);
      const status = expected ? expected.status : null, title = expected ? expected.title : null;
      if (TL.isShown(m, p, T) !== shown || TL.statusAt(p, T) !== status || TL.titleAt(p, T) !== title) {
        if (mismatches++ < 5) {
          console.log('  ' + name + ' ' + p.id + ' at ' + new Date(T).toISOString() + ': shown ' + TL.isShown(m, p, T) + '/' + shown +
            ', status ' + TL.statusAt(p, T) + '/' + status + ', title ' + TL.titleAt(p, T) + '/' + title);
        }
      }
    }
  }
  ok(mismatches === 0, name + ': isShown, statusAt and titleAt equal the brute-force replay (' + mismatches + ' mismatches)');
  return m;
}

compareWithBruteForce('fixture B', FIXTURE_B);
const MODEL_A = compareWithBruteForce('fixture A', FIXTURE_A);

// --- present rules on the back-fill ----------------------------------------------------------
{
  const m = MODEL_A, get = id => m.byId.get(id);
  ok(m.recordingStart === A_R, 'recording starts at the baseline');
  const live = get('feature-brief:new-live');
  ok(live.present && live.born === A_R && live.marks.every(mark => mark.k !== 'created'), 'a page first seen in the baseline is born there without a created mark');
  ok(get('feature-brief:new-done').finishT === A_R, 'a page present in a finish status is settled from recording start');
  const renamed = get(RENAMED);
  ok(renamed.marks.every(mark => mark.t !== A_R), 'a back-filled page named by the baseline gains no mark');
  ok(TL.titleAt(renamed, A_R - 1) !== 'Drop the block set (as recorded)' && TL.titleAt(renamed, A_R) === 'Drop the block set (as recorded)',
    'the PR title holds until recording starts, the recorded title from then');
  ok(TL.statusAt(get(REOPENED), A_R) === 'building' && get(REOPENED).finishT < A_R, 'a resync keeps the finish the back-fill gave');
  const backfillOnly = m.pages.filter(p => p.id.includes(':bf-'));
  ok(backfillOnly.length > 0 && backfillOnly.every(p => p.endedAt === A_R), 'every back-fill-only page ends at recording start');
  ok(get('bug-report:mwjb2nuq-8f9cfc').endedAt === A_R, 'a real back-filled page the baseline does not name ends at recording start');
  ok(get('feature-brief:tail1').endedAt === null && get('feature-brief:tail1').finishT === atR(14), 'a recorded page lives on');
}

// --- Metro layout ----------------------------------------------------------------------------
function checkLayout(name, events) {
  const m = TL.fold(payload(events));
  const layout = TL.layoutMetro(m);
  ok(layout.height > 0, name + ': the layout has a height');
  const trunkRows = new Set(m.pages.filter(p => p.trunk).map(p => p.track));
  const byTrack = new Map();
  for (const p of m.pages) {
    if (p.trunk || p.track === null) continue;
    ok(!trunkRows.has(p.track), name + ': ' + p.id + ' branches onto a trunk row');
    if (!byTrack.has(p.track)) byTrack.set(p.track, []);
    byTrack.get(p.track).push(p);
  }
  let overlaps = 0;
  for (const lanes of byTrack.values()) {
    lanes.sort((a, b) => a.lane0 - b.lane0);
    for (let i = 1; i < lanes.length; i++) if (lanes[i].lane0 < lanes[i - 1].lane1 + 30 * 60000) overlaps++;
  }
  ok(overlaps === 0, name + ': no two lanes overlap on a track (' + overlaps + ' overlaps)');
  let disagreements = 0;
  for (const T of sampleMoments(events, 11)) {
    for (const p of m.pages) {
      const inside = p.shown.some(([from, to]) => from <= T && T < to);
      if (inside !== TL.isShown(m, p, T)) disagreements++;
    }
  }
  ok(disagreements === 0, name + ': shown intervals agree with isShown (' + disagreements + ' disagreements)');
  return m;
}
{
  const m = checkLayout('fixture B', FIXTURE_B), get = id => m.byId.get(id);
  ok(get('feature-brief:h1').track === null && get('epic:e2').track === null, 'pages present and hidden at the baseline get no track');
  const f1 = get('feature-brief:f1');
  ok(get('implementation-plan:ip1').acts[0].y === f1.y, 'a step done after its plan finished sits on the feature track');
  ok(get('testing-plan:tp1').acts[0].y === f1.y, 'a case passed after its plan finished sits on the feature track');
  ok(get('implementation-plan:ip1').settleY === f1.y, 'a plan merges back into its feature');
  ok(get('toc:t1').trunk && f1.settleY === get('toc:t1').y, 'a shipped feature merges back into its trunk');
  ok(f1.marks.filter(mark => mark.k === 'ship')[0].y === f1.y, 'the ship node sits at the end of its own lane');
  ok(f1.marks.filter(mark => mark.k === 'rename')[0].y === get('toc:t1').y, 'a mark after finish sits where the page merged');
}
{
  const m = checkLayout('fixture A', FIXTURE_A), get = id => m.byId.get(id);
  const features = get(FEATURES), first = get('feature-brief:bf-0001');
  ok(features.trunk && get(BUGS).trunk && get('toc:docs').trunk, 'every toc is a trunk');
  ok(first.track !== null && first.track !== features.track && first.finishT !== null && first.settleY === features.y,
    'the first back-filled feature-brief branches off the Features trunk and merges back');
  ok(first.branchY === features.y, 'it branches from the Features trunk');
  ok(get('feature-brief:new-under').track !== null, 'a page revealed later keeps a track');
  ok(get('feature-brief:new-done').track === null && get('feature-brief:new-done').settleY === features.y,
    'a page present and finished is a settled glyph on its parent');
  ok(get('feature-brief:new-live').lane0 === A_R && get('feature-brief:new-live').track !== null, 'a page present and open has a track from recording start');
}

console.log(failures ? failures + ' FAILURES' : 'all checks passed');
process.exit(failures ? 1 : 0);
