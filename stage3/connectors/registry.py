"""Connector registry.

PROVENANCE — pattern KEPT from the helpdesk's ``KBAgent.CONNECTORS``
mapping; the IT sources it pointed at have been removed.

TODO:
    [ ] Add further connectors as they are built, e.g. a mark-scheme
        connector if mark schemes need different parsing from
        specifications, or a worked-examples connector.

All three subjects are now sourced (Isaac Science Biology/Chemistry —
core tier only, no real GCSE content available there; Ada Computer
Science — genuine core + foundation tiers, see connectors/
ada_computer_science.py's module docstring for why it's the odd one out).
"""

from __future__ import annotations

from .ada_computer_science import AdaComputerScienceConnector
from .base import Connector
from .curriculum_docs import CurriculumDocsConnector
from .isaac_science import IsaacChemistryConnector, IsaacScienceConnector

CONNECTORS: dict[str, type[Connector]] = {
    "curriculum_docs": CurriculumDocsConnector,
    "isaac_science": IsaacScienceConnector,  # biology, core tier
    "isaac_chemistry": IsaacChemistryConnector,  # chemistry, core tier
    "ada_computer_science": AdaComputerScienceConnector,  # core + foundation
}
