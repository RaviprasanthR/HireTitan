"""What Mikasa can call (002m research R3), shared later with 007 ``mcp-access``.

This package sits at the composition level, like the ``*_wiring.py`` files: it may use every
feature module's application and infra layers, so each action calls the same use case as the
endpoint it mirrors. Feature modules never import it.
"""
