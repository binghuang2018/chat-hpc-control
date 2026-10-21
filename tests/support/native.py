"""Script helpers used inside a clean wheel-installed test environment."""

HELPERS = '''
import json, io, tarfile, time, uuid, os
from dataclasses import replace
from chat_hpc_control.contracts.auth import CallContext
from chat_hpc_control.contracts.codec import parse_task
from chat_hpc_control.contracts.execution import SubmissionRequest
from chat_hpc_control.sources.bundle import BundleStore
from chat_hpc_control.core.service import build_service
def make_native(name, script, walltime=None):
    own=replace(site,root=site.root/name,engines={"demo":site.engines["demo"]},
       executor=ExecutorConfig("local","example-local",{"max_cpus":2,"max_memory_mib":512}),
       settings={"plugin_allowlist":{"demo":"chat-hpc-demo-engine"}})
    own.root.mkdir(parents=True,exist_ok=True)
    archive=own.root/"source.tar"
    raw=script.encode()
    with tarfile.open(archive,"w") as out:
        item=tarfile.TarInfo("job.py");item.size=len(raw);out.addfile(item,io.BytesIO(raw))
    bundle=BundleStore(own).import_tar(archive)
    task=parse_task(json.dumps({"schema":"chat-hpc-control/task/v1","task_id":name,"engine_id":"demo",
      "engine_options":{},"source":{"kind":"bundle","bundle_id":bundle},"entrypoint":"job.py",
      "resources":{"cpus":1,"memory_mib":64,"walltime_seconds":walltime},"expected_results":None}).encode())
    service=build_service(own)
    context=CallContext("alice",own.site_id,frozenset({"tasks:validate","tasks:submit","tasks:read","results:read"}),
       engines=frozenset({"demo"}))
    validated=service.broker.validate(task,context)
    request=SubmissionRequest(own.site_id,validated.task,validated.manifest_sha256,"intent-1")
    return service,request,context
def terminal(executor,handle,seconds=30):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        observed=executor.query(handle)
        if observed.execution_state in {"COMPLETED","FAILED","CANCELLED","UNKNOWN"}:
            return observed
        time.sleep(.05)
    raise AssertionError("native test did not reach terminal evidence")
'''
