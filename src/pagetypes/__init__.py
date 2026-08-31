"""Page types as data, one module per type.

This package has no import hub: the building blocks live in ``pagetypes.core.*`` and are
imported from those concrete submodules, the registry and its accessors live in
``pagetypes._registry``, and each page type is declared in its own module beside this one.
The init module is intentionally empty of logic - a regular package needs the file, and the
HMR reactive finder resolves the package through it - so that it can never become a hub again.
"""
