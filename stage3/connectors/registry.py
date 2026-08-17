"""Connector registry.

PROVENANCE — pattern KEPT from the helpdesk's connector mapping; the IT
sources it pointed at have been removed. All three in-scope subjects are
sourced: Isaac Science for Biology/Chemistry (core tier only), Ada
Computer Science (core + foundation tiers — see that connector's
docstring for why it's the only one with real foundation content).
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
