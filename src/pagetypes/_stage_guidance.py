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
EPIC_DRAFT = """
draft - the epic exists and nothing has been looked at. This status is for capturing
what the person wants and why, in their words, before anyone researches it. The work
of it:

- Write the summary as the outcome they want, not a solution.
- If they have not said why, ask one open question in their terms with nothing to
  pick from. Do not offer approaches yet: options offered now steer what they tell
  you.
- Record the why as they said it.
- Draw out the goals, non-goals and anti-goals and record them as outcomes, marking
  what you filled in as your proposal. They are what the approaches are judged
  against, so they are written before any approach exists and cannot be fitted to
  one.

No code is read here. Recon belongs to the research agent, so this page's context
stays small. Begin research once the summary, the why and the outcomes are written.
"""

RESEARCHING = """
researching - the intent is captured, and a research agent is finding out what is true
and what could be built, on the epic's solution-research page. This status is for
dispatching that agent and waiting, not for researching. The work of it:

- Create a researcher agent-plan page under the epic at standard capability, linked
  works-on to the research page, with worktree none: the run reads code, it never
  edits it. Its task carries the summary, the why and any answered questions.
- When the research is submitted for judging, create a fresh judge agent-plan page at
  the same capability against the same page. The judge sets the verdict and fires
  report or revise; on revise, redispatch the researcher with the findings.
- Accept a run only from its page. A run that answers with a long reply instead of a
  filled page has failed and is redispatched. Accept each finished agent-plan page,
  because the epic's later gates count every agent-plan page under it.
- Allow one extra round for minor findings; a pass that again turns up only minor
  findings is a pass.

Do not open the research page beyond its digest and its questions. Present the
findings once the research page is reported.
"""

DECIDING = """
deciding - research is in, and this is the conversation that turns it into the
person's choice. It is the one stage where the controller talks the work through with
them. The work of it:

- Read the research digest and questions. Ask each open one here, flagged needsHuman,
  and put them to the person one at a time, building each on their last answer or on
  a research fact and saying what the answer changes. A proposal with your reason
  often beats a question.
- Play back your understanding in short chunks, marking what they said as theirs and
  what you filled in as your proposal, and ask what is wrong or missing. Refine the
  outcomes as the conversation settles them, turning a confirmed proposal into what
  the person said.
- Then, in a message of its own, lay out the approaches with their trade-offs and the
  recommendation and ask which way to go. Record the pick as the chosen approach, and
  the pick itself as an answered question.
- If an answer rules out every approach or changes the ask, reopen research with that
  answer in the researcher's task rather than design on a stale set.

Nothing is designed here. Choosing the approach is the person's gate: drive up to it
and stop.
"""

DESIGNING = """
designing - the person has picked an approach, and a design agent is writing it up on
the epic's solution-design page. This status is for running the design and its check,
not for designing. The work of it:

- Create a designer agent-plan page at capable capability - the one stage making open
  decisions every agent after it inherits - linked works-on to the design page, with
  worktree none. Its task carries the chosen approach ids, the outcomes, the answered
  questions and the research page id.
- When the design is submitted for check, create a fresh reviewer agent-plan page at
  the same capability, handed only the design page. It reads the page cold as the
  builder who must plan from it, records its questions and findings, sets the outcome
  and verdict, and fires markReady or revise.
- On revise, redispatch the designer to sort the builder questions and apply the
  findings. Bring every question it escalates to the person in one message, most
  important first; answer them in this epic's questions, then redispatch the designer
  to fold the answers in and resubmit.
- The check yields one round of questions for the person. A second pass only
  verifies, raising blocking findings at most.

Submit the design for sign-off once the design page is ready.
"""

DESIGN_REVIEW = """
designReview - the design page is ready and frozen, and this is the person's sign-off.
Nothing is decomposed or built until they give it. The work of it:

- Put the design digest in front of them with a link to the design page and the
  decisions marked proposal, so they can check your calls while reading.
- Answer their questions from the page. A change they want goes back through
  requestDesignChanges with their words in the designer's task; a change of approach
  goes back through reconsiderApproach.

"Sounds good" to a digest is not approval of a page they have not opened. Approval is
the person firing approveDesign: drive up to it and stop.
"""

DECOMPOSITION = """
decomposition - the design is signed off. This status is for sealing it and splitting
it into the pages the build agents work from. The work of it:

- Seal the design page first; a design that can still move is not one to split.
- Split along the design's expected changes into feature-briefs, each created under
  the epic itself, not under the Features toc page - the epic's ship gate only sees
  briefs that are its own children. Every expected change is owned by exactly one
  brief and every acceptance criterion is delivered by at least one.
- Turn every interface that crosses between two briefs into a shared contract with an
  owner, its shape copied from the design.
- Create one agent-plan page per build agent under the epic itself too - the epic's
  plan and review gates only see agent-plan pages that are its own children. Give each
  a capability: cheap for mechanical single-file work, standard for ordinary
  multi-file work, capable only for breadth, a critical domain or open design. Its
  task names the design decisions and contracts it touches by id, never the
  session's history.
- The Scheduling section groups the agent-plan pages into the waves the controller
  dispatches them in, consistent with the depends-on links between them: each wave
  leaves a working, verifiable state, and runs at most five agents at once.

If the split shows the design cannot be built as written, reopen the design rather
than patch it in a brief: the person signs the changed design off again.
"""


# --- solution-research and solution-design -----------------------------------
INVESTIGATING = """
investigating - you are the research agent, handed the epic's intent and nothing else.
This page is your whole output: the controller reads its digest, and nobody reads your
reply. The work of it:

- Restate the ask, then read the codebase from where it lands, following callers and
  imports until the blast radius stops growing. Give every recon entry its basis:
  observed when you opened it, inferred when it follows from something you opened,
  assumed when neither.
- Read the outside sources this workspace allows for prior art: libraries, upstream
  documentation, comparable designs.
- Generate several real ways of building it, cull those that work against the why or
  that the code rules out, and keep two or three grounded in the recon. Give each a
  prediction that should hold if it is right and a falsifier that would show it wrong,
  and judge each against the epic's outcomes. Recommend one.
- Turn what only the person can settle into questions; never ask what the code or the
  epic already answers.
- Write the digest last.

Do not design the solution, write code, or run a command on the epic or on any
agent-plan page. Submit for judging once a stranger could choose between the
approaches from this page alone.
"""

JUDGING = """
judging - the research is written, and a fresh judge who did not write it checks it
before anyone relies on it. The work of it:

- Open a sample of the entries marked observed and confirm they say what the page
  claims; one that does not check out is a blocking finding, and so is an inference
  passed off as observed.
- Check the approaches genuinely differ, each grounded in the recon, and that the
  dropped approaches explain the culling. An approach whose falsifier could never be
  observed is a blocking finding.
- Check the digest says nothing the page does not.

Record each problem as a finding, set the verdict afresh, and fire report on pass or
revise otherwise. Minor findings alone are a pass.
"""

DRAFTING = """
drafting - you are the design agent, handed the chosen approach, the epic's outcomes
and answered questions, and the research page to read. This page is what the person
will sign off. The work of it:

- Copy the intent from the epic, then grow the chosen approach into a strategy a
  builder could plan from: the parts, what each is responsible for, how data moves,
  and where pure logic ends and effects begin.
- Record every shaping decision with its alternatives and reason, marking your own
  calls as proposals.
- Write each interface's exact shape, every expected change by path, and acceptance
  criteria a reviewer can verify.
- Design the smallest thing that meets the outcomes: no configurability, extension
  points or generality nobody asked for.
- After a check, resolve each builder question the page, the epic or the research
  already answers, settle each minor one as a proposal decision, and escalate the
  ones only the person can answer; then stop and report which ones wait on them.
  Once their answers are on the epic, resolve those and fold the answers in.

Do not decompose the work or write code. Submit for check once every builder question
is resolved and the digest matches the page.
"""

CHECKING = """
checking - the design is written, and a fresh reviewer reads it as the builder who must
plan from it, without the conversation that produced it. The work of it:

- Read this page, opening the research page only to check the expected changes
  against its recon. Add the questions you would need answered before planning, where
  a wrong guess would change the build, most important first; skip what the page
  leaves to the builder and what you could decide yourself.
- Check the design against the verdict's rubric and record each problem as a finding.
- Set the builder-check outcome and the verdict afresh on every pass.

Fire markReady when the verdict is pass and nothing important is left; otherwise fire
revise. On a second pass, raise only blocking findings and no new questions for the
person.
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
