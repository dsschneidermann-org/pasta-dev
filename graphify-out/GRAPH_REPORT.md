# Graph Report - pasta  (2026-08-23)

## Corpus Check
- 114 files · ~135,876 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1575 nodes · 4267 edges · 57 communities
- Extraction: 92% EXTRACTED · 8% INFERRED · 0% AMBIGUOUS · INFERRED: 341 edges (avg confidence: 0.9)
- Token cost: 144,664 input · 80,043 output

## Community Hubs (Navigation)
- Command Application Tests
- Store Batch & Ref Tests
- Command Engine
- HTML Page Rendering
- Workspace Store Core
- MCP Server Tools
- Retention Cleanup Sweep
- Field & Block Spec Tests
- Page-Type Declarations
- Page-Type Introspection
- Markdown Page Rendering Tests
- Block Kind Validation
- Element Lifecycle Commands
- Dev Server & Live Reload
- Markdown Render Internals
- Statechart States & Validation Docs
- Pasta FSM Evaluation
- Page Read & Create Routes
- Serialization & Pure Core
- Workspace Validation Script
- Error Types & Ref Guards
- Transitions, Actions & Guards Docs
- Library API & Integration Docs
- Diagram Generation Docs
- MCP Server Integration Tests
- Doc Generation Tests
- Page-Type Invariant Tests
- Reader-Writer Lock
- Event & Machine Construction
- Web Route Tests
- State Doc Generation
- Test-Only Type Registry
- Child Page & Reference Rendering
- Feature Brief MCP Probe
- Atomic File Storage
- Statechart IO & Security Docs
- Per-State Doc Rendering
- Behaviour Flags & Error Handling Docs
- Graphify Extraction Spec
- Page-Type Definition Validation
- Graphify Query & Honesty Rules
- FSM Spec & State Guidance
- Graphify Incremental Rebuild
- MCP Protocol Probe
- Statechart Doc Binding
- Graphify Export Targets
- Graph Merge & Copy Semantics
- Internal vs Self Transitions
- Processing Model & Async
- Probe Call Plumbing
- Id Generation
- Markdown Escaping
- Workspace Tree Rendering
- Block Kind Normalization
- Workspace Link Rendering
- Probe Error Handling
- Pytest Test-Mode Fixture

## God Nodes (most connected - your core abstractions)
1. `apply_command()` - 113 edges
2. `Page` - 87 edges
3. `ValidationError` - 85 edges
4. `Store` - 78 edges
5. `make_counter()` - 78 edges
6. `PageType` - 66 edges
7. `create_page()` - 64 edges
8. `get_page_type()` - 64 edges
9. `CommandSpec` - 55 edges
10. `Workspace` - 43 edges

## Surprising Connections (you probably didn't know these)
- `Hyperedge` --semantically_similar_to--> `ElementBlocksSpec`  [INFERRED] [semantically similar]
  .claude/skills/graphify/references/extraction-spec.md → src/pagetypes/__init__.py
- `ExitWorktree State Reset` --semantically_similar_to--> `Sweep`  [INFERRED] [semantically similar]
  .claude/skills/cook/SKILL.md → src/cleanup.py
- `scheduler_enabled()` --semantically_similar_to--> `State Timeout`  [INFERRED] [semantically similar]
  src/cleanup.py → docs/python-statemachine/timeout.md
- `start_scheduler()` --semantically_similar_to--> `Invoke (Background Work on Entry)`  [INFERRED] [semantically similar]
  src/cleanup.py → docs/python-statemachine/invoke.md
- `stop_scheduler()` --semantically_similar_to--> `Invoke Cancellation on Exit`  [INFERRED] [semantically similar]
  src/cleanup.py → docs/python-statemachine/invoke.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Pure Core Modules (No I/O)** — src_model, src_fsm, src_commands, src_serialize, src_describe, src_pagetypes_init [INFERRED 0.85]
- **HTML Template Inheritance Chain** — src_templates_base, src_templates_nav, src_templates_page, src_templates_tree, src_templates_index, src_templates_error [EXTRACTED 1.00]
- **Page-Type Documentation Pipeline** — src_describe_describe_page_type, src_docsgen_render_state_doc, scripts_gen_page_type_docs, docsite_page_types_generated_state_reference, src_templates_nav_model_iframe [INFERRED 0.85]
- **Graphify Pipeline Stages** — claude_skills_graphify_skill_ast_structural_extraction, claude_skills_graphify_skill_semantic_extraction, claude_skills_graphify_skill_community_detection, claude_skills_graphify_skill_graph_health_check, claude_skills_graphify_skill_god_nodes, claude_skills_graphify_skill_html_visualization [EXTRACTED 1.00]
- **Incremental Rebuild Machinery** — claude_skills_graphify_skill_extraction_cache, claude_skills_graphify_references_update_incremental_update, claude_skills_graphify_references_update_manifest_stamping, claude_skills_graphify_references_update_build_merge_replace, claude_skills_graphify_references_hooks_post_commit_hook, claude_skills_graphify_references_add_watch_watch_mode [INFERRED 0.85]
- **Graph Query Surface** — claude_skills_graphify_references_query_query_expansion, claude_skills_graphify_references_query_bfs_traversal, claude_skills_graphify_references_query_dfs_traversal, claude_skills_graphify_references_query_token_budget, claude_skills_graphify_references_query_save_result_feedback_loop, claude_skills_graphify_references_exports_mcp_graph_server [INFERRED 0.85]
- **Core Statechart Concepts** — docs_python_statemachine_states_state, docs_python_statemachine_transitions_transition, docs_python_statemachine_events_event, docs_python_statemachine_actions_action, docs_python_statemachine_guards_condition, docs_python_statemachine_listeners_listener [EXTRACTED 1.00]
- **Hierarchical State Features (3.0)** — docs_python_statemachine_states_compound_state, docs_python_statemachine_states_parallel_state, docs_python_statemachine_states_history_pseudostate, docs_python_statemachine_transitions_cross_boundary_transition, docs_python_statemachine_transitions_transition_priority, docs_python_statemachine_events_done_state_event [EXTRACTED 1.00]
- **Class-Definition Validation Suite** — docs_python_statemachine_validations_exactly_one_initial_state, docs_python_statemachine_validations_no_transitions_from_final, docs_python_statemachine_validations_unreachable_states, docs_python_statemachine_validations_trap_states, docs_python_statemachine_validations_final_state_reachability, docs_python_statemachine_validations_callback_resolution [EXTRACTED 1.00]
- **IO Layer: load, formats, schema, security** — docs_python_statemachine_io_index_load_facade, docs_python_statemachine_io_formats_declarative_format, docs_python_statemachine_io_json_schema_json_schema, docs_python_statemachine_io_security_secure_by_default, docs_python_statemachine_io_formats_scxml [EXTRACTED 1.00]
- **Diagram Toolchain** — docs_python_statemachine_diagram_diagram, docs_python_statemachine_diagram_sphinx_directive, docs_python_statemachine_diagram_mermaid_format, docs_python_statemachine_diagram_dot_graphviz, docs_python_statemachine_diagram_text_representation, docs_python_statemachine_diagram_formatter_api [EXTRACTED 1.00]
- **Pasta Statechart Diagram Binding** — src_statecharts_page_machine_qualname, src_docsgen_diagram_block, docs_python_statemachine_diagram_sphinx_directive, docsite_page_types_statemachine_diagram_directive, docsite_conf [EXTRACTED 1.00]
- **TrafficLight Example Family** — docs_python_statemachine_images_traffic_light_machine_diagram, docs_python_statemachine_images_readme_trafficlightmachine_diagram, docs_python_statemachine_images_traffic_light_machine_cycle_event, docs_python_statemachine_transitions_or_combinator, docs_python_statemachine_events_event [EXTRACTED 1.00]
- **Internal vs External Loop Illustration** — docs_python_statemachine_images_internal_transition_sc_diagram, docs_python_statemachine_images_test_state_machine_internal_diagram, docs_python_statemachine_images_internal_transition_sc_internal_loop, docs_python_statemachine_transitions_internal_transition, docs_python_statemachine_transitions_self_transition [EXTRACTED 1.00]
- **Guarded Workflow Diagram Examples** — docs_python_statemachine_images_oc_machine_processing_order_control_workflow, docs_python_statemachine_images_lab_approval_machine_accepted_approval_workflow, docs_python_statemachine_images_oc_machine_processing_guarded_receive_payment, docs_python_statemachine_guards_condition, docs_python_statemachine_guards_multiple_conditional_transitions [INFERRED 0.85]

## Communities (57 total, 0 thin omitted)

### Community 0 - "Command Application Tests"
Cohesion: 0.05
Nodes (121): Collection, apply_command(), create_page(), field_setter_edges(), legal_commands(), Map each command name to whether it is legal for `page` right now. A command is…, The stage-relevant field-setter `do` edges for `page` in its current status…, Validate and apply one command, returning the resulting page (a fresh copy). (+113 more)

### Community 1 - "Store Batch & Ref Tests"
Cohesion: 0.02
Nodes (73): IllegalCommandError, A command is not legal for this page right now. `legal` is the list of command…, _child(), _child_ids(), _detail(), _page_with_one_item(), fixture, Integration tests for the stateful storage shell (src.store). These exercise… (+65 more)

### Community 2 - "Command Engine"
Cohesion: 0.06
Nodes (75): Content-Gated Transition, Transition Command, _add_block(), _add_element(), _apply(), _apply_element_writes(), BatchContext, _block_array_arg() (+67 more)

### Community 3 - "HTML Page Rendering"
Cohesion: 0.07
Nodes (75): _children_html(), _contents_html(), _element_html(), element_view(), ElementView, _escape(), _field_html(), _link_html() (+67 more)

### Community 4 - "Workspace Store Core"
Cohesion: 0.07
Nodes (35): Page, Workspace, mutatePageBatch(), Run an ordered batch of commands on a page as a single atomic commit (each…, _now(), Any, Rank live pages by a case-insensitive word-prefix match of `query`'s terms…, True if `page` itself or any ancestor is archived - the subtree rule `tree`… (+27 more)

### Community 5 - "MCP Server Tools"
Cohesion: 0.05
Nodes (72): Cook Workflow Skill, Pasta MCP Instruction Bootstrap, ExitWorktree State Reset, Graph MCP Stdio Server, Navigable Knowledge Graph, Pasta Workflow Skill, exception_handler, middleware (+64 more)

### Community 6 - "Retention Cleanup Sweep"
Cohesion: 0.06
Nodes (61): Invoke Cancellation on Exit, FastAPI, classify(), delete_subtree(), _descendants(), expiry_for(), _loop(), Any (+53 more)

### Community 7 - "Field & Block Spec Tests"
Cohesion: 0.06
Nodes (49): _blocks(), ElementBlocksSpec, FieldSpec, _list(), The block declaration for `element_field`, or None when it holds a scalar value., The element field names that hold blocks - what every consumer skips when it is…, The element field whose value heads each of this list's elements, or None when…, A LIST element field that holds an ordered array of blocks instead of a scalar… (+41 more)

### Community 8 - "Page-Type Declarations"
Cohesion: 0.11
Nodes (42): The `architecture` page type., The `bug-report` page type., The `decision-record` page type., The `document` page type., The feature lifecycle: a `feature-brief` and the three children pinned under…, _a(), add_link_cmd(), ArgSpec (+34 more)

### Community 9 - "Page-Type Introspection"
Cohesion: 0.09
Nodes (38): _block_schema(), command_arg_schema(), _command_summary(), describe_fsm(), describe_mutations(), describe_page_type(), Any, Pure introspection: shape a PageType / a page's legal mutations for the tools.… (+30 more)

### Community 10 - "Markdown Page Rendering Tests"
Cohesion: 0.14
Nodes (39): page_text(), A page as Markdown: a title heading, then EVERY declared section and field,…, A flat text projection of a page's content (title + every string value), for…, render_page(), _fields_page_with_specials(), make_counter(), new_blocks(), _page_with_one_item() (+31 more)

### Community 11 - "Block Kind Validation"
Cohesion: 0.07
Nodes (34): BlockKindSpec, collect_ref_ids(), Validate one block against the vocabulary its field declares. A block is an…, Validate an array of blocks against the vocabulary its field declares., Every `{ref: pageId}` page id carried by an arg `value` of the given `content`…, Table width consistency: every row (and `align`, if given) matches the header's…, The kinds this blocks field accepts - its declaration, else every standard…, One block kind a blocks field accepts. `args` None means this kind's standard… (+26 more)

### Community 12 - "Element Lifecycle Commands"
Cohesion: 0.11
Nodes (33): is_valid_status(), The `epic` page type, and the `agent-plan` pinned under it. The two are…, AutoChildSpec, _block_ref_ids(), _boolean(), ChildStateGuard, element_cmds(), ElementFSMSpec (+25 more)

### Community 13 - "Dev Server & Live Reload"
Cohesion: 0.07
Nodes (21): Lock, main(), Entrypoint for the pasta MCP server. Runs as an HTTP server on port 8000 by…, WebSocket, Browser live-reload WebSocket connection manager. This module is deliberately…, ReloaderConnectionManager, build_dev_app(), _patch_session_init() (+13 more)

### Community 14 - "Markdown Render Internals"
Cohesion: 0.12
Nodes (30): _block_inline_text(), _checkbox(), checkbox_state(), _field_content(), _indent_list_content(), _inline_or_text(), _plain(), Any (+22 more)

### Community 15 - "Statechart States & Validation Docs"
Cohesion: 0.10
Nodes (29): Action Execution Order, Active Configuration, done.state Completion Event, DoneData Payload, Classic GoF State Pattern, Coming From the State Pattern, Structural Validation Catches Design Errors, Coming From pytransitions (+21 more)

### Community 16 - "Pasta FSM Evaluation"
Cohesion: 0.10
Nodes (25): dummy_write_computation_times(), patch gen_gallery to disable write_computation_times, send() Event Trigger, Checking Enabled Events, Child State Machines, allowed_events Query, Sending Events, python-statemachine Library (+17 more)

### Community 17 - "Page Read & Create Routes"
Cohesion: 0.10
Nodes (19): Create-Not-Mint Naming Convention, get, Request, get_page_type(), guard_production_type(), Raise if `tag` names a production page type while in test mode - the shared…, Resolve a page type by tag. The hand-authored test-only types resolve too (see…, createPage() (+11 more)

### Community 18 - "Serialization & Pure Core"
Cohesion: 0.20
Nodes (20): Plain JSON File Storage, Pure Core + Stateful Shell, Pure domain dataclasses: `Workspace` and `Page`. Field *values* are plain JSON-…, page_from_dict(), page_to_dict(), Any, Pure serialization: Workspace/Page <-> plain JSON-able dict. Field values are…, workspace_from_dict() (+12 more)

### Community 19 - "Workspace Validation Script"
Cohesion: 0.15
Nodes (21): build_index(), Finding, _has_section_content(), _is_empty_value(), main(), PageIndex, Any, Path (+13 more)

### Community 20 - "Error Types & Ref Guards"
Cohesion: 0.14
Nodes (23): The validated insert/move slot for an anchored, stale-read-safe operation - the…, resolve_anchored_slot(), ConflictError, NotFoundError, PastaError, ProductionTypeInTestError, Exception, Error hierarchy for the pasta core. These are raised by the pure core… (+15 more)

### Community 21 - "Transitions, Actions & Guards Docs"
Cohesion: 0.13
Nodes (23): Action, Callback Dependency Injection, Generic Callbacks, prepare_event Hook, before/on/after Transition Actions, Cleanup / Finalize Pattern, Condition (cond / unless), Boolean Condition Expression (+15 more)

### Community 22 - "Library API & Integration Docs"
Cohesion: 0.13
Nodes (22): API Reference, EventData, TransitionList, TriggerData, Credits, Contributing Guide, Release Process, Translations (+14 more)

### Community 23 - "Diagram Generation Docs"
Cohesion: 0.12
Nodes (21): Sphinx autodoc Integration, Diagram Generation, DOT / Graphviz Output, Formatter API, Mermaid Output Format, statemachine-diagram Sphinx Directive, Current-State Highlighting, Text Representation via format() (+13 more)

### Community 24 - "MCP Server Integration Tests"
Cohesion: 0.18
Nodes (21): call(), _flow_page(), mcp(), fixture, Integration tests for the FastMCP server, driven end-to-end via the in-memory…, test_add_link_via_server(), test_archive_page_via_server(), test_batch_and_next_actions_via_server() (+13 more)

### Community 25 - "Doc Generation Tests"
Cohesion: 0.16
Nodes (19): _bullet(), _field_line(), One markdown list item: a `marker`, its description, and any schema `notes`. A…, Every state reachable from the FSM's initial state, mapped to the shortest…, reachable_states(), _counter(), Unit tests for the pure doc generator (src.docsgen)., A blocks field teaches its vocabulary in the generated docs, because a reader… (+11 more)

### Community 26 - "Page-Type Invariant Tests"
Cohesion: 0.10
Nodes (20): initial_sections(), The empty section/field state a freshly created page of this type starts with., parametrize, The single-home rule: every transition/compound command declares its source…, Every required-content precondition must point at a field the page type…, An element-transition command must fire an event on a field that has an element…, add/set/move/remove-block commands must target a `blocks` field - or, when…, The 'extend to all fields' contract: every list field exposes a reorder_element… (+12 more)

### Community 27 - "Reader-Writer Lock"
Cohesion: 0.13
Nodes (15): A readers-writer lock: many concurrent readers, one exclusive writer. Writer-…, Hold the shared lock; a no-op if this thread already holds the write lock. Do…, Hold the exclusive lock. Reentrant for the thread that owns it., ReadWriteLock, Unit tests for the readers-writer lock (src.rwlock). Pure threading, no I/O:…, A thread holding the write lock may enter read()., Two readers must be able to hold the shared lock at the same time., A reader must not enter while a writer holds the exclusive lock. (+7 more)

### Community 28 - "Event & Machine Construction"
Cohesion: 0.15
Nodes (19): Core Statechart Concepts, Turnstile Example, Event, Event id vs name, event= Transition Parameter, README TrafficLightMachine Diagram, Cycle Event (Green to Yellow to Red), TrafficLightMachine Diagram (+11 more)

### Community 29 - "Web Route Tests"
Cohesion: 0.11
Nodes (4): client(), fixture, Integration tests for the FastAPI HTML routes (src.server web layer). The…, test_set_page_status_rejects_unknown_state()

### Community 30 - "State Doc Generation"
Cohesion: 0.16
Nodes (17): main(), Generate the per-page-type-state Sphinx docs and write them into the docsite.…, all_state_docs(), Every page-type-state doc across the registry, keyed ``<tag>-<state>``., The generated ``states.md`` - a toctree over every state doc, so they are…, render_states_index(), Test-only: enter (or leave) test mode, in which production page types are off-…, set_test_mode() (+9 more)

### Community 31 - "Test-Only Type Registry"
Cohesion: 0.18
Nodes (16): discoverable_registry(), expose_test_types(), Test-only: reveal the hand-authored test-only types to `registered_tags` and…, The advertised page-type tags. The test-only types are excluded unless…, The registry that doc generation enumerates: production only, plus the hand-…, registered_tags(), _test_registry(), parametrize (+8 more)

### Community 32 - "Child Page & Reference Rendering"
Cohesion: 0.16
Nodes (18): The workspace view the renderer needs to turn page ids into titled, annotated…, RefContext, _page_with_children(), _page_with_links(), A bare test-fields Page (empty sections) with the given direct child ids., A bare test-fields Page (empty sections) with the given outgoing links [{to,…, A bare toc Page (no sections) with the given direct child ids., test_render_child_pages_archived_sort_below_active() (+10 more)

### Community 33 - "Feature Brief MCP Probe"
Cohesion: 0.19
Nodes (14): Client, cmd(), elide(), find_features_toc(), main(), Probe, Manual end-to-end probe of the feature-brief workflow over MCP. Drives a real…, One `{command, args}` entry for a mutatePageBatch batch. `command` is… (+6 more)

### Community 34 - "Atomic File Storage"
Cohesion: 0.15
Nodes (10): PathLike, Atomic Temp-File + os.replace Write, PASTA_DATA_DIR Data Directory, Per-Workspace Lock, datetime, IdFactory, Path, Keeps a reader out of the copy that replaces a workspace file. Held per file… (+2 more)

### Community 35 - "Statechart IO & Security Docs"
Cohesion: 0.16
Nodes (15): create_machine_class_from_definition, Dot-Notation Naming Convention, Callback References, Datamodel, Declarative Statechart Format, SCXML Support, System Variables, Trusted Mode (+7 more)

### Community 36 - "Per-State Doc Rendering"
Cohesion: 0.27
Nodes (14): Generated Per-State Reference, _all_states_line(), _arg_signature(), _authoring_section(), _command_line(), _page_type_section(), Any, Pure generation of Sphinx docs for every page type AND every one of its FSM… (+6 more)

### Community 37 - "Behaviour Flags & Error Handling Docs"
Cohesion: 0.16
Nodes (14): allow_event_without_transition, atomic_configuration_update, Behaviour Flags, catch_errors_as_events, enable_self_transition_entries, StateMachine vs StateChart Semantics, Errors Dispatched as Internal Events, Error Handling (+6 more)

### Community 38 - "Graphify Extraction Spec"
Cohesion: 0.18
Nodes (13): Extraction Subagent Prompt Spec, Hyperedge, Deterministic Node ID Format, semantically_similar_to Edge, Vision Image Extraction Rule, Code-Only Update Fast Path, Manifest Stamping Rule, AST Structural Extraction (+5 more)

### Community 39 - "Page-Type Definition Validation"
Cohesion: 0.21
Nodes (9): is_auto_child_type(), PageType, Whether `child_type` is an auto-created (pinned, protected) child of…, Reject a type declaring two do-eligible setters for one (section, field). A…, A field setter (SET_SCALAR / SET_PROSE / ADD_ELEMENT) carries a short…, The page's status-FSM transition table, DERIVED from its transition/compound…, status_transitions(), test_auto_children_are_specs_and_pinned_detection() (+1 more)

### Community 40 - "Graphify Query & Honesty Rules"
Cohesion: 0.20
Nodes (12): Discrete Confidence Score Rubric, Native CLAUDE.md Integration, BFS Traversal Mode, DFS Traversal Mode, Constrained Query Expansion, Query / Path / Explain Flow, Token Budget Cap, EXTRACTED/INFERRED/AMBIGUOUS Audit Trail (+4 more)

### Community 41 - "FSM Spec & State Guidance"
Cohesion: 0.17
Nodes (9): FSMSpec, The stage instruction for `state`, or None when the type declares none for it., A page's status FSM: its state set and initial state ONLY. The transition table…, Carrying a legal_in is not enough - it must name the terminal state. `setNote`…, test_legal_in_override_is_per_state_not_merely_declared(), test_guidance_for_returns_none_for_undeclared_state(), test_state_guidance_normalizes_authored_text(), test_state_guidance_rejects_duplicate_state() (+1 more)

### Community 42 - "Graphify Incremental Rebuild"
Cohesion: 0.31
Nodes (11): URL Ingestion (graphify add), Watch Debounce, Folder Watch Mode, Post-Commit Auto-Rebuild Hook, save-result Feedback Loop, Work Memory / LESSONS.md, Video/Audio Transcription Step, Incremental Update Flow (+3 more)

### Community 43 - "MCP Protocol Probe"
Cohesion: 0.27
Nodes (10): Response, main(), parse_body(), Manual MCP streamable-HTTP probe for the pasta server. Runs the full client…, Decode the JSON-RPC payload from a JSON or text/event-stream response. Returns…, Print one exchange (status, key headers, decoded body) and return the body., Build a JSON-RPC message. Pass request_id=None for a notification (no id)., rpc() (+2 more)

### Community 44 - "Statechart Doc Binding"
Cohesion: 0.18
Nodes (11): One Markdown doc per reachable state of ``page_type``, keyed ``<tag>-<state>``.…, A content-less page of ``page_type`` pinned at ``state`` - enough for…, _seed_page(), state_docs(), page_machine_qualname(), The importable dotted path of the page-status machine bound above for page type…, test_ignore_requirements_does_not_bypass_legal_in_lock(), test_page_machine_qualname_resolves_for_every_registered_type() (+3 more)

### Community 45 - "Graphify Export Targets"
Cohesion: 0.25
Nodes (9): Export Targets, FalkorDB Export, Neo4j Cypher Export, Token Reduction Benchmark, Agent-Crawlable Wiki Export, Self-Composed Whisper Prompt, Cluster-Only Rerun, Community Detection (+1 more)

### Community 46 - "Graph Merge & Copy Semantics"
Cohesion: 0.22
Nodes (8): Verbatim source_file Rule, Cross-Repo Graph Merge, GitHub Repo Clone, Monorepo Subfolder Merge, Replace-on-Re-extract Merge, graph.json Shrink Guard, Copy-Edit-Batch-Overwrite Cycle, A deep copy - the pure command path edits a copy, never the input.

### Community 47 - "Internal vs Self Transitions"
Cohesion: 0.36
Nodes (9): Enter/Exit State Actions, InternalTransitionSC Diagram, internal_loop vs external_loop, OrderControl Payment/Shipping Workflow, TestStateMachine Internal-Transition Diagram, Initial State, Internal Transition, Self-Transition (+1 more)

### Community 48 - "Processing Model & Async"
Cohesion: 0.25
Nodes (9): Async Support, Sync / Async Engine Selection, Initial State Activation, Chained Transitions, Internal / External Event Queues, Macrostep, Microstep, Processing Model (+1 more)

### Community 49 - "Probe Call Plumbing"
Cohesion: 0.31
Nodes (7): Any, One tools/call round-trip; returns the tool's decoded payload or raises…, Run a batch on one page and return the ids it created, in order, nulls dropped., The JSON-RPC message from a JSON body, or the last meaningful frame of an SSE…, The first text block of a tools/call result (where FastMCP puts the payload /…, _result_frame(), _text_content()

### Community 50 - "Id Generation"
Cohesion: 0.33
Nodes (8): _base36(), default_id_factory(), new_id(), new_token(), Id generation - the one impure source of identifiers. Ids look like the…, A time-ordered, collision-resistant token: `<base36-ms>-<random>`., A prefixed id, e.g. `new_id("architecture") -> "architecture:mqtcfkx1-a3f9c1"`., Prefixed id when `prefix` is non-empty (pages), else a bare token (list…

### Community 51 - "Markdown Escaping"
Cohesion: 0.25
Nodes (8): escape_markdown(), Escape a plain-text value so a whole-document Markdown->HTML pass renders it…, test_escape_markdown_escapes_backslash_first(), test_escape_markdown_global_specials_render_as_text(), test_escape_markdown_is_multiline(), test_escape_markdown_neutralises_line_start_blocks(), test_escape_markdown_ordered_list_leaves_no_visible_backslash(), test_escape_markdown_passes_through_empty()

### Community 52 - "Workspace Tree Rendering"
Cohesion: 0.33
Nodes (6): Inline NetworkX Fallback, build_ref_context(), A RefContext over `workspace`: a pageId->title map (archived pages included)…, The whole (non-archived) tree as one Markdown document, nested by depth. Which…, render_tree(), Workspace Tree Template

### Community 53 - "Block Kind Normalization"
Cohesion: 0.40
Nodes (4): _as_block_kinds(), Normalize a declaration: a bare name becomes that standard kind, a spec passes…, A field naming one kind twice is a declaration bug - the second is unreachable., _reject_duplicate_kinds()

### Community 54 - "Workspace Link Rendering"
Cohesion: 0.33
Nodes (6): A `store.tree()` result as a nested Markdown list - every page a link to…, render_workspace_links(), test_render_workspace_links_archived_marker_is_prefix(), test_render_workspace_links_escapes_titles_web_only(), test_render_workspace_links_nested_and_meta(), test_render_workspace_links_show_meta_false()

### Community 55 - "Probe Error Handling"
Cohesion: 0.40
Nodes (4): RuntimeError, ProbeError, initialize -> notifications/initialized, carrying the session id onward., A tool call came back as a JSON-RPC error, an isError result, or an undecodable…

### Community 56 - "Pytest Test-Mode Fixture"
Cohesion: 0.50
Nodes (3): _forbid_production_types_in_tests(), fixture, Pytest configuration for the pasta suite: put the whole run in *test mode*.…

## Ambiguous Edges - Review These
- `_machine_class()` → `Domain Model`  [AMBIGUOUS]
  docs/python-statemachine/models.md · relation: conceptually_related_to
- `Page` → `Domain Model`  [AMBIGUOUS]
  docs/python-statemachine/models.md · relation: conceptually_related_to

## Knowledge Gaps
- **28 isolated node(s):** `Plain JSON File Storage`, `PASTA_DATA_DIR Data Directory`, `Per-Page-Type Status FSM`, `water.css Stylesheet Baseline`, `Obsidian Vault Export` (+23 more)
  These have ≤1 connection - possible missing edges or undocumented components.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `_machine_class()` and `Domain Model`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **What is the exact relationship between `Page` and `Domain Model`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `ValidationError` connect `Error Types & Ref Guards` to `Command Application Tests`, `Store Batch & Ref Tests`, `Command Engine`, `Workspace Store Core`, `Field & Block Spec Tests`, `Graphify Query & Honesty Rules`, `Markdown Page Rendering Tests`, `Block Kind Validation`, `Element Lifecycle Commands`, `Page Read & Create Routes`, `Serialization & Pure Core`, `Web Route Tests`?**
  _High betweenness centrality (0.116) - this node is a cross-community bridge._
- **Why does `PageType` connect `Page-Type Definition Validation` to `Command Application Tests`, `Command Engine`, `HTML Page Rendering`, `Workspace Store Core`, `Field & Block Spec Tests`, `Page-Type Declarations`, `Page-Type Introspection`, `Markdown Page Rendering Tests`, `Element Lifecycle Commands`, `Markdown Render Internals`, `Page Read & Create Routes`, `Serialization & Pure Core`, `Diagram Generation Docs`, `Page-Type Invariant Tests`, `State Doc Generation`, `Test-Only Type Registry`, `Statechart IO & Security Docs`, `Per-State Doc Rendering`, `FSM Spec & State Guidance`, `Statechart Doc Binding`?**
  _High betweenness centrality (0.085) - this node is a cross-community bridge._
- **Why does `Page` connect `Workspace Store Core` to `Command Application Tests`, `Child Page & Reference Rendering`, `Command Engine`, `HTML Page Rendering`, `Per-State Doc Rendering`, `Retention Cleanup Sweep`, `Page-Type Introspection`, `Markdown Page Rendering Tests`, `Statechart Doc Binding`, `Graph Merge & Copy Semantics`, `Markdown Render Internals`, `Page Read & Create Routes`, `Serialization & Pure Core`, `Transitions, Actions & Guards Docs`, `Library API & Integration Docs`?**
  _High betweenness centrality (0.085) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `apply_command()` (e.g. with `Copy-Edit-Batch-Overwrite Cycle` and `Page`) actually correct?**
  _`apply_command()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 34 inferred relationships involving `Page` (e.g. with `_add_block()` and `_add_element()`) actually correct?**
  _`Page` has 34 INFERRED edges - model-reasoned connections that need verification._