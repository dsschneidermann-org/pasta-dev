"""Regression tests for the HMR reload-error capture (src._hmr_debug).

The module re-executes on every hot reload, so it keeps the hooks it wraps on `sys` and must
capture them only once - otherwise each reload would wrap the previous wrapper.
"""

import importlib
import sys

import src._hmr_debug as hmr_debug


def test_reexecuting_the_module_keeps_the_original_hooks():
    excepthook_orig = getattr(sys, "_hmr_dbg_excepthook_orig")
    unraisable_orig = getattr(sys, "_hmr_dbg_unraisable_orig")

    reloaded = importlib.reload(hmr_debug)

    assert getattr(sys, "_hmr_dbg_excepthook_orig") is excepthook_orig
    assert getattr(sys, "_hmr_dbg_unraisable_orig") is unraisable_orig
    assert reloaded._excepthook_orig is excepthook_orig
    assert reloaded._unraisable_orig is unraisable_orig
    assert sys.excepthook is reloaded._excepthook
    assert sys.unraisablehook is reloaded._unraisablehook
