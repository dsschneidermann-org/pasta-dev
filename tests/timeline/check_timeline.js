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

console.log(failures ? failures + ' FAILURES' : 'all checks passed');
process.exit(failures ? 1 : 0);
