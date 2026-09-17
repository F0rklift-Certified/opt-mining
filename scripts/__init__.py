"""Operational runner scripts for regenerating pipeline data products.

These are thin orchestration wrappers around the frozen ``pipeline`` package.
They exist to re-run stages over a different coverage (e.g. full NSW) or to
sequence a re-freeze/re-validate, without duplicating or mutating pipeline logic.
"""
