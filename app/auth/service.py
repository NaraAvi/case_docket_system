"""Identity verification services for the citizen authentication workflow.

This project uses a prototype identity provider pattern: a domain-level
identity verification service delegates to a concrete registry implementation.
The current implementation is a development-only Test Identity Registry used
for synthetic citizen logins.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from seed_data.test_citizens import TEST_CITIZENS, TEST_CONSTABLES, TEST_DETECTIVES, TEST_IPIDS, TEST_STATION_COMMANDERS


class IdentityVerificationService:
    """Protocol-like abstraction for identity verification providers."""

    def verify_identity(self, test_id: str) -> Optional[Dict[str, object]]:
        raise NotImplementedError("Identity verification provider must be implemented.")

    def get_identity(self, test_id: str) -> Optional[Dict[str, object]]:
        raise NotImplementedError("Identity lookup provider must be implemented.")

    def list_identities(self) -> List[Dict[str, object]]:
        raise NotImplementedError("Identity listing provider must be implemented.")


class TestIdentityRegistry(IdentityVerificationService):
    """Development identity provider backed by synthetic test identity data.

    This registry intentionally represents a fake identity provider and is not a
    real government or external verification service.
    """

    __test__ = False

    def __init__(self):
        self._citizen_identities = {
            identity["test_id"]: {
                "test_id": identity["test_id"],
                "full_name": identity["full_name"],
                "role": identity["role"],
                "active": bool(identity.get("active", True)),
                "access_state": "ACTIVE",
                "source": identity.get("source", "development_test"),
            }
            for identity in TEST_CITIZENS
        }
        self._constable_identities = {
            identity["test_id"]: {
                "test_id": identity["test_id"],
                "full_name": identity["full_name"],
                "role": identity["role"],
                "active": bool(identity.get("active", True)),
                "access_state": "ACTIVE",
                "source": identity.get("source", "development_test"),
            }
            for identity in TEST_CONSTABLES
        }
        self._detective_identities = {
            identity["test_id"]: {
                "test_id": identity["test_id"],
                "full_name": identity["full_name"],
                "role": identity["role"],
                "active": bool(identity.get("active", True)),
                "access_state": "ACTIVE",
                "source": identity.get("source", "development_test"),
            }
            for identity in TEST_DETECTIVES
        }
        self._station_commander_identities = {
            identity["test_id"]: {
                "test_id": identity["test_id"],
                "full_name": identity["full_name"],
                "role": identity["role"],
                "active": bool(identity.get("active", True)),
                "access_state": "ACTIVE",
                "source": identity.get("source", "development_test"),
            }
            for identity in TEST_STATION_COMMANDERS
        }
        self._ipid_identities = {
            identity["test_id"]: {
                "test_id": identity["test_id"],
                "full_name": identity["full_name"],
                "role": identity["role"],
                "active": bool(identity.get("active", True)),
                "access_state": "ACTIVE",
                "source": identity.get("source", "development_test"),
            }
            for identity in TEST_IPIDS
        }
        self._identities = {
            **self._citizen_identities,
            **self._constable_identities,
            **self._detective_identities,
            **self._station_commander_identities,
            **self._ipid_identities,
        }

    def verify_identity(self, test_id: str) -> Optional[Dict[str, object]]:
        if not test_id:
            return None
        identity = self._identities.get(str(test_id))
        if identity is None or not identity.get("active", True):
            return None
        if str(identity.get("access_state", "ACTIVE")).upper() == "REVOKED":
            return None
        return dict(identity)

    def get_identity(self, test_id: str) -> Optional[Dict[str, object]]:
        if not test_id:
            return None
        identity = self._identities.get(str(test_id))
        if identity is None:
            return None
        return dict(identity)

    def revoke_access(self, test_id: str) -> Optional[Dict[str, object]]:
        if not test_id:
            return None
        identity = self._identities.get(str(test_id))
        if identity is None:
            return None
        identity["access_state"] = "REVOKED"
        return dict(identity)

    def restore_access(self, test_id: str) -> Optional[Dict[str, object]]:
        if not test_id:
            return None
        identity = self._identities.get(str(test_id))
        if identity is None:
            return None
        identity["access_state"] = "ACTIVE"
        return dict(identity)

    def list_identities(self) -> List[Dict[str, object]]:
        return [
            dict(identity)
            for identity in {
                **self._citizen_identities,
                **self._constable_identities,
                **self._detective_identities,
                **self._station_commander_identities,
                **self._ipid_identities,
            }.values()
        ]

    def list_constables(self) -> List[Dict[str, object]]:
        return [dict(identity) for identity in self._constable_identities.values()]

    def list_detectives(self) -> List[Dict[str, object]]:
        return [dict(identity) for identity in self._detective_identities.values()]

    def list_station_commanders(self) -> List[Dict[str, object]]:
        return [dict(identity) for identity in self._station_commander_identities.values()]

    def list_ipids(self) -> List[Dict[str, object]]:
        return [dict(identity) for identity in self._ipid_identities.values()]


class AuthService:
    """Placeholder session/auth container for future role-based workflows."""

    def __init__(self, registry: Optional[IdentityVerificationService] = None):
        self._registry = registry or TestIdentityRegistry()
        self._users = {}

    def register_user(self, user_id, user):
        self._users[user_id] = user

    def get_user(self, user_id):
        return self._users.get(user_id)

    def verify_test_identity(self, test_id: str):
        return self._registry.verify_identity(test_id)
