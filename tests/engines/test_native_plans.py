from dataclasses import replace
import importlib
import json
from chat_hpc_control.contracts.codec import parse_task
from pathlib import Path
import pytest
from chat_hpc_control.contracts.config import SiteConfig,RuntimeConfig,ExecutorConfig
from chat_hpc_control.contracts.plugins import PrepareContext,ValidationContext
from chat_hpc_control.contracts.task import FrozenTask,ResolvedTask


def engine(name):
    try: return importlib.import_module('chat_hpc_control.engines.'+name).create_plugin()
    except ModuleNotFoundError: pytest.fail('native engine is missing: '+name)


@pytest.mark.parametrize('name,suffix',[('pyscf','.py'),('orca','.inp'),('molpro','.inp')])
def test_arbitrary_native_input(sample_task,tmp_path,name,suffix):
    task=replace(parse_task(json.dumps(sample_task).encode()),engine_id=name,entrypoint='nested/calculation'+suffix)
    site=SiteConfig('example',tmp_path,{}, {name:RuntimeConfig('/configured/native')},ExecutorConfig('local','test'))
    plugin=engine(name)
    assert plugin.validate(ResolvedTask(task,{task.entrypoint:b'arbitrary molecule and method'},{}),ValidationContext(site)).valid
    frozen=FrozenTask(task,{},'a'*64,tmp_path/'frozen')
    plan=plugin.prepare(frozen,PrepareContext(site,tmp_path/'run',site.engines[name]))
    assert plan.argv[0]=='/configured/native'
    assert plan.cwd==tmp_path/'run/work'
    assert all('shell' not in str(x) for x in plan.argv)
    assert str(plan.cwd/task.entrypoint) in plan.argv
    if name=='pyscf': assert '-B' in plan.argv
    assert 'raw-only' in plugin.info().profiles


def test_molpro_mpi_comes_only_from_site(sample_task,tmp_path):
    plugin=engine('molpro')
    task=replace(parse_task(json.dumps(sample_task).encode()),engine_id='molpro',entrypoint='job.inp')
    runtime=RuntimeConfig('/site/molpro',mpi_argv=('/site/mpiexec','-n','2'))
    site=SiteConfig('example',tmp_path,{}, {'molpro':runtime},ExecutorConfig('local','test'))
    plan=plugin.prepare(FrozenTask(task,{},'a'*64,tmp_path/'inputs'),PrepareContext(site,tmp_path/'run',runtime))
    assert plan.argv[:4]==('/site/mpiexec','-n','2','/site/molpro')


def test_engine_options_cannot_inject_argv():
    for name in ('pyscf','orca','molpro'):
        schema=engine(name).info().options_schema
        assert schema['additionalProperties'] is False
        assert not {'argv','shell','environment','cwd'} & schema['properties'].keys()
