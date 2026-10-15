"""Ray-tracing platform stages for the outfit converter.

``prepare_classic`` leaves a ``natives/x64`` tree. ``upgrade_to_rt`` leaves
``natives/stm``. The outfit converter owns packaging.
"""

from .converter import prepare_classic, upgrade_to_rt

__all__ = ["prepare_classic", "upgrade_to_rt"]
