"""
Lightweight tree-state dataclasses for tracking container hierarchy.

These live in their own module so that headless code (e.g. the scripting
session) can use them without pulling in Qt or VTK.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from typing import Dict, List
from dataclasses import dataclass, field

__all__ = ["TreeState", "TreeStateData"]


@dataclass()
class TreeState:
    """Legacy tree structure (deprecated - kept for backward compatibility)."""

    #: {'Group 1': ['uuid1', 'uuid2'], ...}
    groups: Dict[str, List[str]] = field(default_factory=dict)
    #: {'Group 1', 'uuid1', ...}
    root_order: Dict[str, int] = field(default_factory=dict)
    #: ['uuid3', 'uuid4', ...]
    root_items: List[str] = field(default_factory=list)

    def get_all_uuids(self):
        """Get all UUIDs currently in the tree."""
        uuids = set(self.root_items)
        for group_uuids in self.groups.values():
            uuids.update(group_uuids)
        return uuids

    def to_tree_state_data(self) -> "TreeStateData":
        """Convert legacy TreeState to new TreeStateData format."""
        state = TreeStateData()

        state.root_items = [None] * len(self.root_order)
        for uuid, (index, group_name) in self.root_order.items():
            state.root_items[index] = uuid

            if group_name is not None:
                state.group_names[uuid] = group_name
                state.groups[uuid] = self.groups[group_name]
        return state


@dataclass()
class TreeStateData:
    """Minimal tree structure tracking."""

    #: Maps group UUIDs to list of geometry UUIDs
    groups: Dict[str, List[str]] = field(default_factory=dict)
    #: Maps group UUIDs to display names
    group_names: Dict[str, str] = field(default_factory=dict)
    #: Top-level items in display order (mix of group UUIDs and geometry UUIDs)
    root_items: List[str] = field(default_factory=list)

    def get_all_uuids(self):
        """Get all UUIDs currently in the tree."""
        uuids = set()
        for item in self.root_items:
            uuids.update(self.groups.get(item, [item]))
        return uuids

    def remove_uuid(self, uuid: str):
        """Remove a UUID from the tree. Can be either group or item"""
        self.root_items = [x for x in self.root_items if x != uuid]

        if uuid in self.group_names:
            self.group_names.pop(uuid)
            self.groups.pop(uuid, None)

        for k in self.groups.keys():
            self.groups[k] = [x for x in self.groups[k] if x != uuid]
