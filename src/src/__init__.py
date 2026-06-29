"""Compatibility namespace for legacy internal imports.

The project uses a standard ``src/`` layout where users should import
``product_evidence_harness`` directly. Some generated internal modules still use
``src.product_evidence_harness``. This namespace keeps those imports working
when only ``<repo>/src`` is on ``sys.path``.
"""
