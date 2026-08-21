# Page types

Every pasta page is an instance of a **page type** that fixes its sections, its
fields, its legal commands, and a **status finite-state machine**. A page advances
through its states only by firing the transition commands its type declares - and,
for some transitions, only once the required content is present.

The reference below is generated directly from the registered page types - one page
per page-type *state*, each with the status machine (rendered with the
`statemachine-diagram` directive) navigated to that state, the transitions legal out
of it, and the type's full schema captured from `describePageType`. Regenerate with
`scripts/gen_page_type_docs.py`.

```{toctree}
:caption: Contents
:titlesonly:

page-types/states.md
```
