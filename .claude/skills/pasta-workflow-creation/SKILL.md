---
name: pasta-workflow-creation
description: Brainstorm a new pasta workflow as a page type in pseudocode - its fields, statuses, gates and stage guidance - without reading the pasta source or setting anything up. Use when the user wants to design, sketch or rethink a workflow, process or page type.
---

# Pasta workflow creation

Design the workflow the user describes as a pasta page type, using the brief below.
This is design on paper:

- Don't read the project's source code, install anything or start a server. The brief
  is the whole model.
- If the pasta MCP is loaded, you may call `listPageTypes` and `describePageType` to see
  the existing types and pick the neighbours for the `instead:` line. Don't create pages.
- Restate the workflow in one sentence first. If who signs off or what counts as done is
  unclear, ask once before designing; otherwise state your assumptions and go.

Hand back what section 6 of the brief lists.

---

You are designing a *page type*: a reusable, typed document that also runs a workflow.
Work only with the model and pseudocode notation below. Do not write Python, name
libraries, or discuss installing, hosting or storing anything. A person will turn your
design into the real system later.

## 1. What a page type is

A page type is declared as data, not code. It has six parts:

1. **Identity**: a kebab-case tag (`dependency-upgrade`), a display name, and one
   paragraph saying when to use this type and which neighbouring type to use instead
   when it doesn't fit.
2. **Sections and fields**: the page's shape. Each section holds typed fields. Every
   field has an *instruction*, the text an agent reads when it is told to fill that field.
3. **Commands**: the only way a page ever changes. There is no free-form editing.
4. **A status lifecycle**: a finite state machine over the page's status. Every edge
   is fired by a command.
5. **Guidance**: optional prose per status saying what the stage is for, plus optional
   *workspace slots* (for example "how this team merges" or "which test runner to use")
   that each workspace fills in and that appear at chosen statuses.
6. **Relationships** (optional): child pages created with the parent, and guards that
   tie one page's progress to another's.

### Field kinds

| Kind    | Holds                                                         | Example |
|---------|---------------------------------------------------------------|---------|
| scalar  | one short value, optionally restricted to an enum of choices  | `component`, `verdict: enum(ready \| needs-changes)` |
| prose   | a paragraph of text                                           | `summary` |
| list    | ordered elements; each is a record of named fields and gets an id | `criteria {text}`, `contracts {name, owner, shape}` |
| blocks  | structured rich text: paragraphs, headings, lists, code, tables, quotes, links to other pages | `details` |
| fixed   | text set by the type itself; no command can write it          | a standing notice |

A list element can also have:
- **its own lifecycle**, e.g. `todo -> done | skipped`, `pending -> passed | failed | skipped`,
  `open -> answered`. One state can be drawn as a checked box.
- **flags** that a command sets, e.g. `stale`, `needsHuman`.
- **a checked reference** to an element on another page, which must exist (e.g. a spec's
  decision points at a question id on its parent brief).

### Command kinds

Every command has a name, arguments, an *agency* (`agent`, `human` or `either`), and
optionally the statuses it is allowed in. Names follow the field they write:

- `set<Field>` writes a scalar or prose field.
- `add<Noun>` / `remove<Noun>` / `reorder<Noun>`, and optionally `edit<Noun>`, manage a
  list. The noun is singular: `addCriterion`.
- An **element transition** moves one element through its own lifecycle (`markStepDone`,
  `answerQuestion`).
- A **flag setter** sets a flag on one element (`escalateQuestion`, `markCommitStale`).
- Block add/remove/reorder edit a blocks field. There is no in-place replace: remove,
  then add at the same position.
- A **transition** moves the page's status along one edge (`beginGrounding`,
  `submitForReview`, `ship`).
- A **compound** runs some authoring commands and then exactly one transition, all at
  once (`close` = record the final commit and close). It cannot fire a second transition.
- Every type gets `addLink` (a typed link to another page) and `setTitle` for free.

### The lifecycle

- One initial status and one or more **terminal** statuses. In a terminal status, all
  content commands are frozen and only transitions (like `reopen`) remain. A content
  command can opt back in by naming the terminal status as one it is allowed in.
- Each edge is declared once, on the transition that fires it: event, source
  status(es), destination, agency.
- An edge can **require** fields to be non-empty before it fires. This checks only that
  the field has content, not what the value is.
- A content command can be **locked** to some statuses (a review verdict only during review).
- Every status must be reachable from the initial status, and only terminal statuses
  may lack an exit.
- A status and an event may share a name (`open` can be both).

### Relationships across pages

- **Pinned children** are declared on the parent and created in the same step as the
  parent (a feature brief creates its spec, implementation plan and testing plan).
- **Ordinary children** are created later, as the work needs them (an epic's feature
  briefs, and one agent-plan page per agent it dispatches).
- A **child guard** holds a parent's transition until its direct children of a given type
  are in an accepted set of states (ship waits until every plan step is done or skipped
  and every test case has passed or been skipped). It ignores archived children and
  fails while no live child of its type exists, so a parent can't pass a gate over
  children it never created. Archiving a child is how it is dropped.
- A **parent guard** keeps a child locked until its parent reaches a given status (no plan
  steps can be written until the brief is in planning).
- There is no gate on the states of elements on the same page. To require "every step
  is done", put the steps on a child page and give the parent a child guard.
- To make one sibling child wait for another, add a status to the parent. Never order
  them by nesting one child under another: guards only see direct children, so a
  moved child leaves its parent's guard with none of its type, and that transition is
  held shut.

## 2. How the workflow drives an agent

You do not write a script of steps. The system recomputes what comes next from the
declaration after every change and gives the agent four lists:

- **do**: agent transitions that are legal now, plus the setters for fields that a
  transition *out of the current status* requires, each with that field's instruction.
- **blocked**: agent transitions that can't fire yet, with the reason (missing fields,
  an unfinished child, the parent status still needed).
- **humanGates**: human edges. The agent works up to them and stops.
- **attention**: list elements waiting on a person, such as an escalated open question.

What this means for your design:
- **The agent is only prompted to fill a field in a stage if the transition leaving that
  stage requires it.** If work belongs to a stage, put its field in that exit edge's
  `requires`. Work that isn't a field (writing code, running tests) belongs in the
  status guidance.
- Element transitions, flag setters, removes and reorders never appear in `do`. The
  agent finds them when it asks what it can run on a page.
- Field instructions and status guidance *are* the agent's instructions. Write them as
  directives.
- Use a human gate wherever a person must sign off. Make everything else an agent edge
  so the work keeps moving.
- Give every review stage a send-back edge (`requestChanges`, `reviseDecomposition`) so
  problems found in review go back to the right stage instead of being patched past it.

## 3. Notation

```
pagetype <tag> "<Display name>"
  use-when: <one sentence>
  instead:  <other-type> for <case>; <other-type> for <case>

  section <key> "<Name>"
    <field>: scalar | scalar enum(a | b) | prose | blocks | fixed "<text>"
      > <instruction the agent reads>
    <field>: list {<f1>, <f2>, <flag>?}
      lifecycle: <state> -> <state> | <state>     checkbox: <state>
      ref <f1> -> <other-type>.<section>.<field>
      > <instruction>
    <field>: ...   locked-to: <status>, <status>

  children: <type>, <type>                        # pinned, created with this page

  lifecycle
    initial:  <status>
    terminal: <status>, <status>
    <from>[|<from>] --<event>/<agency>--> <to>
        requires: <section.field>, ...
        guard child <type>: <section.field> all in {<state>, <state>}
        guard parent: status in {<status>, ...}
        steps: <command>(<args>)                  # makes the edge a compound

  commands                                        # only the non-obvious ones; set/add/remove/reorder are implied
    <name>: element <section.field>  <state> -> <state>
    <name>: flag <section.field>.<flag>

  guidance <status>: |
    <stage prose>

  workspace-slot <name> at <status>, ...: "<what a workspace fills in>"
```

If your workflow needs something this model can't express, write it on its own line as
`EXTENSION: <what> - <why the workflow needs it>`. Never quietly pretend it exists.

## 4. Writing the prose

**Field instruction**: say what one entry is, how specific it has to be, and what goes
wrong if it is vague.
> Each one part of the system this epic touches, named as a real path you confirmed
> exists. A component missed here is one no agent owns.

**Status guidance** follows one shape:
```
<status> - what state the work is in, and what this status is for. The work of it:
- a concrete activity
- a concrete activity
What is deliberately not due here. When to fire the exit transition, and which
send-back edge to use if something turns up.
```

## 5. Worked example

```
pagetype dependency-upgrade "Dependency upgrade"
  use-when: moving one third-party dependency to a new version, including fixing what the move breaks.
  instead:  simple-change for a version bump with nothing to fix; feature-brief when the upgrade
            is a vehicle for new behaviour.

  section target "Target"
    package: scalar
      > The one dependency being upgraded, named exactly as the manifest names it.
    versions: scalar
      > From and to, as "1.4.2 -> 2.0.0". Pin the exact target; "latest" is not a version.
  section why "Why"
    body: prose
      > What the upgrade buys or what staying costs: a CVE, an end-of-life date, a feature
      > something else is waiting on.
  section impact "Impact"
    breaking: list {text}
      > Each one breaking change from the upstream changelog that this codebase actually hits,
      > with its call site. A changelog entry nothing here uses does not belong.
    affected: list {path}
      > Each one file or module that has to change, confirmed by reading it.
  section work "Work"
    steps: list {text}
      lifecycle: todo -> done | skipped     checkbox: done
      > Each one edit small enough to verify on its own, in the order it will be made.
  section review "Review"
    verdict: scalar enum(ready | needs-changes)     locked-to: review
      > ready only when the full test suite passed on the new version in a run you saw.
    commits: list {sha, message, stale?}            locked-to: upgrading, review, done, closed
      > Each commit that delivers the upgrade, recorded as you make it. Flag it stale after a rebase.

  lifecycle
    initial:  draft
    terminal: closed, abandoned
    draft       --beginAssessment/agent-->  assessing   requires: target.package, target.versions, why.body
    assessing   --planUpgrade/agent-->      upgrading   requires: impact.breaking, impact.affected, work.steps
    upgrading   --submitForReview/agent-->  review
    review      --approve/agent-->          done        requires: review.verdict
    review|done --requestChanges/either-->  upgrading
    done        --close/human-->            closed      steps: recordCommit(sha, message)
    draft|assessing|upgrading|review --abandon/human--> abandoned
    closed      --reopen/agent-->           upgrading

  commands
    markStepDone:    element work.steps      todo -> done
    skipStep:        element work.steps      todo -> skipped
    markCommitStale: flag review.commits.stale

  guidance assessing: |
    assessing - the target version is chosen and nothing has changed yet. This status is for
    finding out what the move actually breaks here, before any edit. The work of it:
    - Read the upstream changelog between the two versions and keep only the entries this
      codebase hits, each with its call site.
    - Find every file that touches the dependency and read it; list the ones that must change.
    - Break the work into steps small enough to verify one at a time.
    Nothing is edited here. Plan the upgrade once a stranger could make the edits from this
    page alone.

  workspace-slot testingTool  at upgrading: "the test runner and command this workspace uses"
  workspace-slot mergeProcess at done:      "how this workspace integrates finished work"
```

What the agent sees as the page moves:
- **draft**: do = `setPackage`, `setVersions`, `setWhy`; blocked = `beginAssessment`
  (needs those fields); humanGates = `abandon`.
- **assessing**: do = `addBreaking`, `addAffected`, `addStep`; blocked = `planUpgrade`.
- **upgrading**: do = `submitForReview` only. Nothing is required here, so the actual
  editing is driven entirely by this status's guidance. Steps are marked with
  `markStepDone`, which never appears in `do`.
- **review**: do = `setVerdict`; blocked = `approve` until a verdict is set.
- **done**: humanGates = `close`. The agent stops here.

Two limits this example exposes:
- `approve` only checks that a verdict exists, so `needs-changes` would not block it.
  The guidance has to say to use `requestChanges` in that case.
- `submitForReview` cannot wait for every step to be done, because the steps are on the
  same page. Moving them to a pinned child with a child guard would fix that, which is
  why a feature brief keeps its plan on a separate page.

## 6. What to hand back

1. The declaration in the notation above.
2. A state diagram (Mermaid `stateDiagram-v2`).
3. A walk-through: for each non-terminal status, what is in do, blocked and humanGates
   when the page arrives there.
4. The self-check below, answered item by item.

## Self-check

- The type's description says when to use it and what to use instead.
- Every status is reachable from the initial status, and every non-terminal status has an exit.
- Each stage's field work appears in its exit edge's `requires`; non-field work is in its guidance.
- Human gates sit exactly where a person must sign off, and abandoning is a human edge.
- Every review stage has a send-back edge.
- Every field instruction is specific enough for a stranger to act on.
- Locks are deliberate: verdicts only in review, records only once the work has started.
- Any "all items done" gate uses a child page and a child guard; siblings are ordered
  through a parent status.
- Every child guard names children that will exist when it is checked: it fails while
  none of its type is live.
- Anything the model can't express is marked `EXTENSION:`.
