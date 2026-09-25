"""Development / test-only synthetic citizen identities.

These are intentionally fake identities for prototype authentication workflows.
They are not real-world identity records and must not be treated as verified
South African or government identities.
"""

TEST_CITIZENS = [
    {
        "test_id": "2200223333111",
        "full_name": "Demo Citizen One",
        "role": "citizen",
        "active": True,
    },
    {
        "test_id": "2200223333112",
        "full_name": "Demo Citizen Two",
        "role": "citizen",
        "active": True,
    },
    {
        "test_id": "2200223333113",
        "full_name": "Demo Citizen Three",
        "role": "citizen",
        "active": True,
    },
]

TEST_CONSTABLES = [
    {
        "test_id": "2200223333114",
        "full_name": "Demo Constable One",
        "role": "constable",
        "active": True,
        "source": "development_test",
    }
]

TEST_DETECTIVES = [
    {
        "test_id": "2200223333115",
        "full_name": "Demo Detective One",
        "role": "detective",
        "active": True,
        "source": "development_test",
    }
]

TEST_STATION_COMMANDERS = [
    {
        "test_id": "2200223333116",
        "full_name": "Demo Station Commander One",
        "role": "station_commander",
        "active": True,
        "source": "development_test",
    }
]

TEST_IPIDS = [
    {
        "test_id": "2200223333117",
        "full_name": "Demo IPID Officer One",
        "role": "ipid",
        "active": True,
        "source": "development_test",
    }
]

__all__ = [
    "TEST_CITIZENS",
    "TEST_CONSTABLES",
    "TEST_DETECTIVES",
    "TEST_STATION_COMMANDERS",
    "TEST_IPIDS",
]
