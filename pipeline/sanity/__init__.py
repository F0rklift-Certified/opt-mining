"""S1-12 validation / sanity-check stage (`sanity`).

The pipeline's terminal stage. It reads the Sprint 1 outputs READ-ONLY and
reports whether the results are plausible against known reality. It is distinct
from the structural cross-domain checks in ``pipeline/validate.py`` and runs
last in the stage sequence.

(The full stage docstring is authored in task 13.3.)
"""
