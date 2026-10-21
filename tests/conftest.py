import copy

import pytest


@pytest.fixture
def sample_task():
    return {
        "schema": "chat-hpc-control/task/v1",
        "task_id": "water-001",
        "engine_id": "pyscf",
        "engine_options": {},
        "source": {"kind": "bundle", "bundle_id": "sample-bundle"},
        "entrypoint": "job.py",
        "resources": {"cpus": 2, "memory_mib": 512, "walltime_seconds": None},
        "expected_results": None,
    }


@pytest.fixture
def clone():
    return copy.deepcopy
