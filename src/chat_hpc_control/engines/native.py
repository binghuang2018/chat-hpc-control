"""Original native engine adapters; no software or legacy source is bundled."""

import hashlib
import os
from pathlib import Path
import subprocess
from ..contracts.execution import ExecutionPlan
from ..contracts.plugins import PluginInfo,ProbeReport,ValidationReport
from ..sources.base import checked_paths
from .parsers.common import failure


class NativeEngine:
    def __init__(self,name,profiles):
        self.name,self.profiles=name,profiles

    def info(self):
        digest=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        properties={'profile':{'type':'string','enum':list(self.profiles)}}
        for key in ('result_file','output_file','gradient_file'):
            properties[key]={'type':'string','minLength':1,'maxLength':512}
        return PluginInfo(self.name,'chat-hpc-control','0.1.0',digest,profiles=self.profiles,
                          options_schema={'type':'object','additionalProperties':False,'properties':properties})

    def probe(self,runtime):
        args=runtime.version_args
        if self.name=='pyscf':args=('-B','-c','import pyscf; print(pyscf.__version__)')
        try:
            env={'PATH':os.defpath,'LANG':'C.UTF-8',**runtime.environment}
            result=subprocess.run([runtime.executable,*args],env=env,stdin=subprocess.DEVNULL,
                                  capture_output=True,timeout=10,close_fds=True)
            if result.returncode or len(result.stdout)+len(result.stderr)>65536:raise ValueError('probe rejected')
            version=(result.stdout+result.stderr).decode(errors='replace').strip()
            if not version:raise ValueError('empty version')
            return ProbeReport(True,version,{'program_sha256':hashlib.sha256(Path(runtime.executable).resolve().read_bytes()).hexdigest()})
        except (OSError,ValueError,subprocess.SubprocessError):
            return ProbeReport(False,'unavailable',{},('configured native runtime or license unavailable',))

    def validate(self,task,context):
        for key in ('result_file','output_file','gradient_file'):
            if key in task.task.engine_options:checked_paths([task.task.engine_options[key]])
        return ValidationReport(task.task.entrypoint in task.files,task.task)

    def prepare(self,task,context):
        work=context.run_root/'work';runtime=context.runtime
        entry=str(work/task.task.entrypoint)
        identity={}
        if self.name=='pyscf':argv=(runtime.executable,'-B',entry)
        elif self.name=='orca':
            argv=(runtime.executable,entry)
            identity={'normal_termination':{'file':'stdout.log','marker':'ORCA TERMINATED NORMALLY'}}
        else:
            argv=(*runtime.mpi_argv,runtime.executable,'-n',str(task.task.resources.cpus),'-d',str(work/'scratch'),'-o',str(work/'molpro.out'),entry)
            identity={'normal_termination':{'file':'molpro.out','marker':'Molpro calculation terminated'}}
        return ExecutionPlan(argv,work,runtime.environment,('*',),task.task.resources,self.name,identity)

    def parse(self,snapshot,contract):
        from .parsers.common import options
        from .parsers import pyscf_json,orca_single,molpro_table,molpro_xml
        try: profile=options(snapshot).get('profile',self.profiles[0])
        except (OSError,ValueError,KeyError):return failure('raw-only')
        if profile=='raw-only':return failure(profile,'RAW_ONLY_NO_NUMERICAL_CERTIFICATION')
        if profile not in self.profiles:return failure(profile,'PROFILE_UNSUPPORTED')
        if self.name=='pyscf':return pyscf_json.parse(snapshot,contract)
        if self.name=='orca':return orca_single.parse(snapshot,contract,profile=profile)
        return (molpro_table if profile=='molpro-table-v1' else molpro_xml).parse(snapshot,contract)
