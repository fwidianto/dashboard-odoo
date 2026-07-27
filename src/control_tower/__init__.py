"""Read-only Control Tower Health package.

The package snapshots native Odoo identifiers into PostgreSQL and exposes
SOP-validation read models. It never writes to Odoo.
"""

from src.control_tower.relation_extractor import ControlTowerRelationExtractor
from src.control_tower.service import ControlTowerService

__all__ = ["ControlTowerRelationExtractor", "ControlTowerService"]
