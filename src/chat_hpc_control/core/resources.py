"""Validate requests without inventing a timeout or a hard reservation."""

from ..contracts.errors import ControlError
from ..contracts.execution import ExecutorCapabilities
from ..contracts.task import ResourceRequest


def validate_resources(request: ResourceRequest, capabilities: ExecutorCapabilities) -> ResourceRequest:
    for value in (request.cpus, request.memory_mib):
        if type(value) is not int or value <= 0:
            raise ControlError("RESOURCE_UNSUPPORTED", "positive integer resources are required")
    if request.cpus > capabilities.max_cpus or request.memory_mib > capabilities.max_memory_mib:
        raise ControlError("RESOURCE_UNSUPPORTED", "request exceeds site resource capacity")
    walltime = request.walltime_seconds
    if walltime is None:
        if not capabilities.accepts_unlimited_walltime or capabilities.max_walltime_seconds is not None:
            raise ControlError("RESOURCE_UNSUPPORTED", "executor does not accept unlimited walltime")
    elif (type(walltime) is not int or walltime <= 0
          or (capabilities.max_walltime_seconds is not None and walltime > capabilities.max_walltime_seconds)):
        raise ControlError("RESOURCE_UNSUPPORTED", "walltime exceeds supported policy")
    return request
