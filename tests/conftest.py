"""Pytest configuration for the pasta suite: put the whole run in *test mode*.

Test mode (``src.pagetypes._registry.set_test_mode``) puts the hand-authored ``test-*`` fixtures
(``src.testtypes``) in place of the PRODUCTION page types, which become off-limits: they do not
resolve (``get_page_type``), are not listed (``registered_pagetypes`` - hence the
``describePageType`` listing and doc-gen enumeration), and a page of one cannot be created. Any
attempt raises ``ProductionTypeInTestError``, steering the author to exercise new capabilities on a
fixture instead - always preferring an existing one. Entering the mode empties ``REGISTRY`` itself,
so a test cannot depend on a production type by reading the map directly either.

The flag is set here at import, ahead of collection, because a test module resolves the fixture page
types it works on at module level. Nothing restores it: the flag lives for the process, and the
process is the run. A test that needs the production types asks for the ``production_mode`` fixture
below.
"""

import pytest

# Imported before the flip on purpose: this module binds one status machine per production page type
# at import, reading REGISTRY, which entering test mode empties. Its classes are built and cached
# here while the production types are still in place.
import src.statecharts  # noqa: F401
from src.pagetypes._registry import set_test_mode

set_test_mode(True)


@pytest.fixture
def production_mode():
    """Leave test mode for one test, so it sees the production registry a live server serves.
    Restored afterwards so the setting does not leak into the rest of the suite."""
    set_test_mode(False)
    yield
    set_test_mode(True)
