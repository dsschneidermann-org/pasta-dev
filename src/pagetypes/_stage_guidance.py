"""The stage instructions a page type hands an agent on entering a status.

A page type declares these on its FSM as `status_guidance`. They live here rather than
inline so one working discipline can reach several page types, and so the text can be
read and revised as prose instead of between a page type's sections and commands. The
leading underscore sorts this module above every page-type module that draws on it.

A constant is named for its status. A bare name is the only text for that status anywhere;
a name carrying a page-type prefix is one type's own take on a status name that several
types claim.

Text is authored indented and normalized by `FSMSpec.__post_init__`, which dedents and
strips it exactly as it does a field description.
"""


# The label the focused page's stage guidance is read behind wherever it is surfaced, so it is
# told apart from the workspace guidance texts alongside it.
PAGE_STATUS_GUIDANCE = "PAGE STATUS GUIDANCE: "


# --- feature-brief -----------------------------------------------------------
GROUNDING = """
grounding - the summary is written and nothing else is known yet. This status is for
reading the real repository and recording what is actually there. The work of it:

- Find the code this feature touches and read it: the function, the file, the
  callers. Understand why it exists, not just what it does. A component whose
  purpose you cannot state is one you are not ready to plan against.
- Record only what you confirmed by opening it. Every component, constraint,
  conflict and stale doc here is read out of this repository, never inferred from a
  name or remembered from somewhere else.
- Follow callers and imports outward until the blast radius stops growing, and note
  as you go which components hold pure logic and which perform effects.
- Turn whatever reading could not settle into a question rather than an assumption.
  An unsurfaced assumption is the most expensive thing to carry out of this status.

No code is edited here and no design is started. If the summary turns out to be
wrong or underspecified once you can see the code, say so now, while nothing has
been built on it.
"""

SPEC = """
spec - the grounded base is recorded, and the design is settled once, in the
feature-spec child, before a single step or case exists. The work of it:

- Update the summary and update the page title to the correct understanding of the
  work and escalate any design questions early to the user now.
- Author the spec from the grounded base: the behaviour, the interfaces with their
  exact signatures, the data shapes, the states, the error paths. Decide everything
  a plan would otherwise have to decide for itself.
- Draw the line between pure logic and effects while designing rather than after.
  Decide what is a function of its inputs alone and what needs I/O, storage, the
  clock or randomness, and give each side its own interfaces. The rules live on the
  pure side; the effectful side stays thin enough to hold none of its own.
- Spec the smallest thing that delivers the summary. No configurability, extension
  points or generality nobody asked for, and no abstraction over a single use.
- Answer the brief's questions and record each decision with the alternatives it
  rejected and why, so a settled question is not reopened mid-build.
- Escalate what only a person can settle instead of settling it on their behalf.

Seal the spec once it is settled; sealing is what unlocks planning. Steps and cases
are not written here, because a design still moving is not one to plan against.
"""

PLANNING = """
planning - the spec is sealed and is now turned into an implementation plan and a
testing plan detailed enough to build from without deciding anything further. The
work of it:

- Write each step as one action a skilled stranger to this codebase could finish in
  a few minutes, naming the exact files and carrying the real content it needs.
  Steps are read out of order and alone, so repeat detail rather than refer back.
- Give every step its verification: what will be run, and what it should print or
  return. A step with no way to tell whether it worked is not yet a step.
- Order the work so the pure logic is built and tested before the effectful code
  that calls it, and keep a step on one side of that line: a step that adds a rule
  changes pure logic, a step that wires it to storage or the network changes the
  shell around it.
- Plan the failure paths the spec implies alongside the happy one - empty inputs,
  missing values, malformed data, boundaries - and say what the volume this will
  really see does to the approach.
- Ask rather than guess. A question is cheap here and expensive once a plan exists.
  Record and escalate questions to the user now.

Keep both plans to what the spec asks for and nothing besides. Mark each ready when
it is complete; submitting the plan needs both plans ready and the spec still
sealed.
"""

PLAN_REVIEW = """
plan-review - the plan is written, and this is the last point at which fixing it is
still cheap. This status is for reading the plan against the spec, not for building.
The work of it:

- Check every spec requirement against a step that delivers it, and every step
  against a spec requirement that asked for it. A requirement no step covers and a
  step nothing asked for are both findings.
- Check that the testing plan can actually fail: cases that assert real behaviour,
  that cover the spec's error paths, and that reach the pure logic directly instead
  of through a mock.
- Check that the plan is not larger than the problem, and that the pure and
  effectful sides stayed separate in it.
- Check that the steps do not update documentation as that is a later activity once
  the implementation has landed.
- Record each finding AND make the edit its action names, so the plan and this
  record agree. A finding recorded but never applied is worse than one never
  raised.

Set the verdict honestly: needs-changes when an implementer would build the wrong
thing or get stuck, needs-human-decision when a question has to go to a person.
Wording and style preferences are not grounds to withhold build-ready.
"""

BUILDING = """
building - the plan is approved, and this is where code is written. Work the steps
in their order and let the plan, not improvisation, decide what gets built. The work
of it:

- Work test-first: write the failing test, watch it fail, write the least code that
  passes it, watch it pass, commit. Mark a step done or a case passed only from a
  run you actually saw.
- Keep the pure logic pure. Decisions, derivations and transformations are functions
  of their arguments, with no I/O, no clock, no randomness and no reaching into
  shared mutable state, and the code that performs effects stays a thin shell that
  calls them and applies what they return. Where a step tangles the two, split them
  rather than reach for a mock.
- Name things for what they mean. A longer name that carries intent beats a short
  one that loses it, and an argument keeps its caller's name unless renaming
  genuinely clarifies. Comments say why, not what.
- Stay surgical. Touch only what the step needs; leave adjacent code, comments and
  formatting exactly as found, and match the style already there even where you
  would have chosen otherwise. Remove only the imports and helpers your own change
  orphaned, and raise anything else you notice as a conflict or a question instead
  of fixing it in passing.
- Handle the realistic failure cases the plan named, and flag a limitation you are
  knowingly leaving in rather than let it be discovered later.

Anything the plan did not anticipate is a question, or a reopened plan, not a quiet
improvisation. Record each commit as you make it.
"""

FEATURE_BRIEF_REVIEW = """
review - the build is done, and this is the last stop before it is marked done and
left for the human ship gate.
This status is for verifying, not for finishing off. The work of it:

- Re-read the spec's design section and confirm every requirement it states is
  actually implemented, not merely planned.
- Confirm every implementation-plan step is done and every testing-plan case passed
  against a test that genuinely ran. A case marked passed without a run you saw is
  the one failure this gate exists to catch.
- Confirm nothing that worked before is broken now, and that the diff carries only
  what the plan called for: an unrelated change here is a change nobody reviewed.
- Confirm the pure logic stayed free of effects and the shell around it stayed free
  of rules.
- Remove tests that have now run but are conditioned on removed parts of the code,
  such as asserting that a removed field no longer exists: once the removal is
  verified they only pin the previous implementation.
- Review the comments added for the change. Avoid verbosity of comments and avoid
  naming the specifics of other parts of code and instead keep comments to general
  principles and intents. Comments should only refer to the current code, not the
  previous implementation. Uppercase words and emphasis markers are inappropriate in
  tone and single line comments that are self-evident by code should be removed, as
  should wordy explanations of well-known technology concepts.

Three things are deliberately not part of this status, so do not start them here:
following the merge process happens at done, not before; recording commits happens
after ship, once the shas are final; and reconciling the documentation pages the brief
named as going stale also happens at ship.

If any of this turns up outstanding work, use requestChanges to go back to building
rather than mark it done with a known gap.
"""


FEATURE_BRIEF_DONE = """
done - the build is verified and the work is done. It is not merged, not shipped and
not signed off: this status says the agent has nothing left to build, and it says
nothing more than that. The work of it:

- Update the README.md or other file-based docs that need to be ready at the gate.
- Update the recorded commits if their shas moved, flagging as stale any sha that has
  left history. If none moved, there is nothing to do.
- Follow the merge process guidance beside this text, if this workspace configured
  one, and leave the pull request url on the page if that produces one. If there is no
  merge process, there is nothing to do.

Reconciling the documentation pages the brief named as going stale waits for ship too:
the sign-off is what authorizes both, and doing either here would cross the gate.
Shipping is a human gate: drive up to it and stop. If anything turns up outstanding,
use requestChanges to go back to building rather than leave a known gap at the gate.
"""

# --- epic --------------------------------------------------------------------
DECOMPOSITION = """
decomposition - the grounded base is recorded, and the epic is now split into the pages
its agents work from. Create each of them as a child of this epic, then schedule them:

- Each feature-brief is created under the epic itself, not under the Features toc page -
  the epic's ship gate only sees briefs that are its own children.
- Each agent-plan page is created under the epic itself too, one per dispatched agent -
  the epic's plan and review gates only see agent-plan pages that are its own children.
- The Scheduling section groups the agent-plan pages into the waves the controller
  dispatches them in, consistent with the depends-on links between them.
"""

# --- spike -------------------------------------------------------------------
SPIKE_DRAFT = """
draft - the spike exists and nothing has been looked at. This status is for capturing
what the user wants and why, in their words, and the directions worth investigating,
before anyone researches it. The work of it:

- Write the summary as the outcome they want, not a solution.
- If they have not said why, ask one open question in their terms with nothing to
  pick from. Do not offer approaches yet: options offered now steer what they tell
  you.
- Record the why as they said it.
- Draw out the goals, non-goals and anti-goals and record them as outcomes, marking
  what you filled in as your proposal. They are what the directions are judged
  against, so they are written before any direction exists and cannot be fitted to
  one.
- Then brainstorm the solution directions with them: two to four genuinely different
  kinds of solution, asking for theirs first and marking yours as proposal. Give each
  a scope saying what it would change or add and what it assumes, so the agent that
  investigates it knows what to look for. Two directions that would send an
  investigator to the same code with the same question are one.

No code is read here. Recon belongs to the agents investigating each direction, so
this page's context stays small. Begin research once the summary, the why, the
outcomes and the directions are written.
"""

RESEARCHING = """
researching - the intent and the directions are captured, and one investigator per
direction is finding out what is true and what that direction would take, each on a
solution-investigation page of its own. This status is for dispatching those agents
and waiting, not for researching. The work of it:

- Create one solution-investigation page under the spike per direction, titled with
  the direction's name, and one investigator agent-plan page per investigation at
  standard capability, linked works-on to it. Its task carries the summary, the why,
  the direction's id and scope and any answered questions. Its worktree is none, or a
  throwaway spike worktree of its own when testing the direction needs code run;
  spike code is never integrated.
- Dispatch the investigators together: they share nothing and can run at once.
- Once every investigation is submitted for judging, create one fresh judge
  agent-plan page at the same capability, linked works-on to every investigation
  page. The judge sets each page's verdict and fires report or revise on each; on
  revise, redispatch that investigator with its findings, then the judge.
- Accept a run only from its page. A run that answers with a long reply instead of a
  filled page has failed and is redispatched. Accept each finished agent-plan page,
  because presenting the findings waits until every agent-plan page under the spike
  is accepted.
- Allow one extra round for minor findings; a pass that again turns up only minor
  findings is a pass. To drop a direction, archive its investigation page.

Do not open an investigation page beyond its digest, its viability and its
questions. Present the findings once every investigation page is reported.
"""

DECIDING = """
deciding - the investigations are in, and this is the conversation that turns them
into the user's choice. It is the one stage where the controller talks the work
through with them. The work of it:

- Read each investigation's digest, viability and questions, and the judge's
  findings. Ask each open question here, flagged needsHuman, and put them to the user
  one at a time, building each on their last answer or on an investigation's fact and
  saying what the answer changes. A proposal with your reason often beats a question.
- Play back your understanding in short chunks, marking what they said as theirs and
  what you filled in as your proposal, and ask what is wrong or missing. Refine the
  outcomes as the conversation settles them, turning a confirmed proposal into what
  the user said.
- Then, in a message of its own, lay out the directions with their trade-offs and
  your recommendation, and ask which way to go. Each investigator argued for one
  direction, so the comparison is yours. Record the pick as the chosen approach by
  its investigation's page id, and the pick itself as an answered question.
- If an answer rules out every direction or changes the ask, reopen research with
  that answer - adding a direction or redispatching an investigation - rather than
  hand off a stale pick.

Nothing is specified or planned here. Choosing the approach is a human gate: drive
up to it and stop.
"""

BRIEFING = """
briefing - the user has picked a direction, and the spike now hands it off as one
feature-brief for another agent to specify, plan and build. The work of it:

- Create one feature-brief under this spike's own parent, next to the spike and not
  under it, titled with the outcome the user wants.
- Write its summary as that outcome, from this spike's summary, why and outcomes,
  and name the chosen direction in one sentence.
- Add each answered question on this spike that bears on the build to the brief's
  questions, and answer it there in the user's words - the approach pick among them -
  so the brief's spec records them and they are not reopened.
- Link the brief to this spike with role researched-in, so whoever plans it can open
  the investigations, then link this spike to the brief with role created-feature.

Do not ground, specify or plan the brief, and do not start an agent on it: it is left
in draft for whoever plans it. Hand off once the created-feature link is in place.
"""

# --- solution-investigation --------------------------------------------------
INVESTIGATING = """
investigating - you are the investigator for one solution direction of the spike,
handed its intent and that direction's scope and nothing else. This page is your
whole output: the controller reads its digest, and nobody reads your reply. The work
of it:

- Record the direction's id and restate it, then read the codebase from where this
  direction would land, following callers and imports until its blast radius stops
  growing. Give every recon entry its basis: observed when you opened it, inferred
  when it follows from something you opened, assumed when neither.
- Read the outside sources this workspace allows for prior art that bears on this
  direction: libraries, upstream documentation, comparable designs.
- Sketch how the direction would be built here, cull the variants of it that the code
  or the why rules out, and assess it against every outcome on the spike.
- Test it: write what should hold if it is right and what would show it wrong, then
  check that by reading or, when your assignment names a spike worktree, by running
  code there. Spike code is never integrated.
- Make the strongest honest case for this direction, and call it not-viable when that
  is what you found: a dead direction reported early is the cheapest result.
- Turn what only the user can settle into questions; never ask what the code or the
  spike already answers.
- Write the digest last.

Stay inside your direction: another direction is another agent's. Do not design the
solution, change code outside your spike worktree, or run a command on the spike or on
any agent-plan page. Submit for judging once a stranger could compare this direction
with the others from this page alone.
"""

JUDGING = """
judging - every investigation of the spike is written, and one fresh judge who wrote
none of them checks them side by side before anyone relies on them. The work of it,
on each investigation page:

- Open a sample of the entries marked observed and confirm they say what the page
  claims; one that does not check out is a blocking finding, and so is an inference
  passed off as observed.
- Where two investigations state contradicting facts about the same code, open it
  and record a blocking finding on the page that is wrong, naming the other.
- Check the page stays inside its direction, its sketch is grounded in its recon,
  every outcome on the spike is assessed, and its test result is backed by its
  evidence. A falsifier that could never be observed is a blocking finding.
- Check the investigations are comparable - the same outcomes, the same cost sizes -
  and record two that came back as the same solution as a minor finding on both.
- Check the digest says nothing the page does not.

Record each problem as a finding, set the verdict afresh, and fire report on pass or
revise otherwise, page by page. Minor findings alone are a pass.
"""

# --- simple-change and bug-report, shared ------------------------------------
REVIEW = """
review - the work is written, and this is the last stop before it is marked done and
left for the human close gate. This status is for verifying, not for finishing off. The
work of it:

- Re-read what the page said the work was and confirm every part of it is actually
  implemented rather than merely intended: each acceptance criterion on a change, the
  reported behaviour on a bug.
- Confirm each check against a run you actually saw. A test you believe passes is the
  one failure this gate exists to catch, so run it.
- Confirm nothing that worked before is broken now, and that the diff carries only what
  the work called for: an unrelated change here is a change nobody reviewed.
- Confirm the pure logic stayed free of effects and the shell around it stayed free of
  rules.
- Remove tests that have now run but are conditioned on removed parts of the code,
  such as asserting that a removed field no longer exists: once the removal is
  verified they only pin the previous implementation.
- Review the comments added for the change. Avoid verbosity of comments and avoid
  naming the specifics of other parts of code and instead keep comments to general
  principles and intents. Comments should only refer to the current code, not the
  previous implementation. Uppercase words and emphasis markers are inappropriate in
  tone and single line comments that are self-evident by code should be removed, as
  should wordy explanations of well-known technology concepts.

Two things are deliberately not part of this status: rebasing onto main happens at
close, not before, and the commit is recorded by close itself, so there is nothing to
record here. If any of this turns up outstanding work, use requestChanges to go back to
open rather than mark it done with a known gap.
"""


DONE = """
done - the work is written, verified and done. It is not merged, not closed and not
signed off: this status says the agent has nothing left to build, and it says nothing
more than that. The work of it:

- Update the README.md or other file-based docs that need to be ready at the gate.
- Follow the merge process guidance beside this text, if this workspace configured
  one, and leave the pull request url on the page if that produces one. If there is no
  merge process, there is nothing to do.

Nothing is built here and no commit is recorded: close records it. Closing is a human
gate, and closing is where the work is actually merged - drive up to that gate and
stop. If anything turns up outstanding, use requestChanges to go back to open rather
than leave a known gap at the gate.
"""

# --- simple-change -----------------------------------------------------------
SIMPLE_CHANGE_DRAFT = """
draft - the change has been asked for and nothing is written down yet. This status is
for saying what changes and why, precisely enough that someone else could start from
the page alone. The work of it:

- Name the one component the change touches. If it needs a second, this is not a
  simple change and belongs in a feature-brief before anything more is written here.
- State the behaviour today and the behaviour you want in its place. A summary naming
  only the new behaviour leaves the reader guessing what it replaces.
- Say who asked and what they actually asked for, so the reason survives the moment
  that prompted it.
- Write acceptance criteria that can come out false: the new behaviour, and the
  nearby behaviour that must keep working. A criterion settled by opinion is not one.
- Say here if the ask looks wrong, or bigger than it sounds, while nothing has been
  built on it.

Nothing is edited here. Open the change once the page would let a stranger to this
codebase start work from it.
"""

SIMPLE_CHANGE_OPEN = """
open - the change is described, and this one status carries it from reading the code to
a change that works. There is no separate grounding, spec or planning stage here, so
the discipline those would enforce has to be kept in this one. The work of it:

- Read the code the change touches before editing it: the function, its callers, why
  it exists. Follow callers and imports outward until the blast radius stops growing.
  A change made against a guess is what this status exists to prevent.
- Keep it the size it was scoped at. If the reading shows the work spans components,
  needs a design settled first, or wants a plan, raise that rather than let a simple
  change grow into an unplanned feature.
- Work test-first: write the failing test, watch it fail, write the least code that
  passes it, watch it pass. Each acceptance criterion should end up with something
  that would fail if the behaviour regressed.
- Keep the pure logic pure. Decisions, derivations and transformations are functions
  of their arguments, with no I/O, no clock, no randomness and no reaching into
  shared mutable state, and the code that performs effects stays a thin shell that
  calls them and applies what they return.
- Stay surgical. Touch only what the change needs; leave adjacent code, comments and
  formatting exactly as found, and match the style already there even where you would
  have chosen otherwise. Anything else you notice is raised, not fixed in passing.

Ask rather than guess, and flag a limitation you are knowingly leaving in rather than
let it be discovered later. Submit for review once the change is written, not once it
is intended.
"""


# --- bug-report --------------------------------------------------------------
BUG_REPORT_DRAFT = """
draft - a defect has been noticed and the report does not exist yet. This status is for
making it reproducible by someone who was not there. The work of it:

- Name the symptom you can observe, specific enough to tell this defect from a similar
  one. The cause you suspect and the fix you have in mind are not the summary.
- Record where it was seen: the component, the platform with versions, and the version
  or commit sha, so the report stays pinnable to a point in history.
- Write the repro as ordered actions from a stated starting state, with the exact
  commands, inputs and data, ending on the step that exposes the defect. A repro
  nobody else can follow is the most common reason a report goes nowhere.
- Ground the expected behaviour in something outside your own judgement: a spec line,
  a doc, a passing test, an established convention. Without that the report is an
  opinion.
- Quote the observed behaviour rather than paraphrase it - the literal message, stack
  trace, exit code or wrong output - and say whether it reproduces every time.

No fix is attempted here and no cause is asserted. Open the report once someone else
could reproduce the defect from the page alone.
"""

BUG_REPORT_OPEN = """
open - the report is written, and this one status carries the defect from reproducing it
to a fix that holds. There is no separate grounding, spec or planning stage here, so
the discipline those would enforce has to be kept in this one. The work of it:

- Reproduce it yourself first, by the recorded steps. A fix written against a failure
  you never saw is a guess, and a repro that does not reproduce is itself the finding -
  record that rather than quietly fixing something else.
- Find the cause by reading the code and following it outward, not by matching the
  shape of the symptom. Fix the cause: a symptom suppressed where it surfaced leaves
  the defect in place under a new name.
- Work test-first: write the test that fails for the reason the report names, watch it
  fail, write the least code that makes it pass, watch it pass. That test is what stops
  the defect coming back.
- Keep the pure logic pure and the effectful shell thin, and stay surgical - touch only
  what the fix needs, leave adjacent code, comments and formatting exactly as found,
  and raise anything else you notice rather than fixing it in passing.
- Say what the fix does not cover: a related path left broken, an intermittent case you
  could not reproduce, a workaround taken where a real fix was too large.

If the cause turns out to be a design problem rather than a defect, that is a feature
brief, not a larger bug fix. Submit for review once the fix is written and its test
genuinely ran.
"""


# --- architecture ------------------------------------------------------------
ARCHITECTURE_AUTHORING = """
authoring - documents a part of the system that already exists, written by reading
that code rather than recalling it. The work of it:

- Fix the boundary first: one part, one granularity, a job stated in one line. If
  that line needs an "and", it is two nodes.
- Describe what is there today. Aspirational architecture belongs in a feature
  brief, and a page mixing the two describes neither.
- Write what one file cannot show: why it exists, where its boundary runs, what
  crosses it, what must stay true. Point at a symbol rather than copy it.
- Say which side of the pure/effectful line the node sits on, and where that line
  runs inside it. A reader deciding where new behaviour belongs needs that first.
- Write invariants that can be checked and broken, with what breaks when violated.
  "Stays consistent" is not one.
- Record dependencies in the direction this node experiences them, naming what
  crosses the boundary.
- Confirm each code reference by opening it, then record the commit you read at.

Why it is shaped this way belongs in a decision record, linked from here. Keep the
page at the scale of its siblings, and when the code moves on mark it stale rather
than leave it describing an older system - a stale page is locked until markCurrent
brings it back here.
"""


# --- decision-record ---------------------------------------------------------
DECISION_RECORD_AUTHORING = """
authoring - captures why one decision was taken, while the reasons are still in
someone's head. The shape it produces belongs on an architecture page; the reasoning
that shape cannot show belongs here. The work of it:

- One decision per record, titled with the position taken rather than the topic:
  "store sessions in the database", not "session storage".
- Write the context first, for someone who was not there: the forces, the
  constraints, what was traded against what. It is worth the most in a year and
  skipped the most often.
- State the decision in the active voice, before any detail. A reader should not
  have to infer it from a discussion of the options.
- Record the options weighed and what ruled each out. Without a rejected
  alternative, nothing stops the question being reopened.
- Give consequences both ways. Only benefits reads as advocacy to whoever inherits
  the cost.
- Say where the decision moves the line between pure logic and effectful code - an
  architecture page can show that boundary but not explain it.
- Fill in date, scope and deciders, so a later reader can weigh how much still
  applies.
"""
