"""Hercules build compiler — renders the neutral ``src/`` tree into per-target ``dist/`` plugins.

Layering (mandatory for the mutation gate): ``parse``/``render``/``model_map``/``serialize`` are
pure string/dataclass transforms with no filesystem access; ``layout``/``cli`` are the thin FS
boundary that reads ``src/`` and writes ``dist/``.
"""
