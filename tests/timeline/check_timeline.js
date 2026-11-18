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

console.log(failures ? failures + ' FAILURES' : 'all checks passed');
process.exit(failures ? 1 : 0);
