"""Pytest configuration for the pasta suite: put the whole run in *test mode*.

Test mode (``src.pagetypes._registry.set_test_mode``) puts the hand-authored ``test-*`` fixtures
(``src.testtypes``) in place of the PRODUCTION page types, which become off-limits: they do not
resolve (``get_page_type``), are not listed (``registered_pagetypes`` - hence the
``describePageType`` listing and doc-gen enumeration), and a page of one cannot be created. Any
attempt raises ``ProductionTypeInTestError``, steering the author to exercise new capabilities on a
fixture instead - always preferring an existing one.

The flag is set here at import, ahead of collection, because a test module resolves the fixture page
types it works on at module level - so the registry must already be the fixtures' by the time the
module is imported. Nothing restores it: the flag lives for the process, and the process is the run.
A module that needs the production types (doc generation) steps out of test mode with a fixture of
its own.
"""

from src.pagetypes._registry import set_test_mode

set_test_mode(True)
