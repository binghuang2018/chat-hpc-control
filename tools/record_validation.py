"""Capture an explicit offline verification command, log and installed versions."""
import argparse,hashlib,importlib.metadata as metadata,json,platform,re,subprocess,sys
from pathlib import Path


def source_digest():
    root=Path(__file__).resolve().parents[1];digest=hashlib.sha256()
    paths=[root/'pyproject.toml']
    for directory in ('src','tests','examples'):
        paths.extend(p for p in (root/directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix in {'.py','.json','.toml','.in'})
    for path in sorted(paths):
        digest.update(path.relative_to(root).as_posix().encode()+b'\0'+path.read_bytes()+b'\0')
    return digest.hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--name',required=True);parser.add_argument('--evidence',type=Path,required=True);parser.add_argument('command',nargs=argparse.REMAINDER)
    args=parser.parse_args();command=args.command
    if command and command[0]=='--':command=command[1:]
    if not command:parser.error('command is required')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+',args.name):parser.error('unsafe name')
    args.evidence.mkdir(parents=True,exist_ok=True)
    log=args.evidence/(args.name+'.log')
    before=source_digest()
    with log.open('w') as stream:
        process=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,text=True)
    if source_digest()!=before:
        raise RuntimeError('source changed during validation; retain log but do not record PASS')
    content=log.read_text(errors='replace')
    summaries=re.findall(r'^.*\d+ passed.*$',content,re.M)
    versions={'python':platform.python_version()}
    for name in ('chat-hpc-control','jsonschema','pytest','build','hatchling','twine','httpx','mcp','openai','anthropic','google-genai'):
        try:versions[name]=metadata.version(name)
        except metadata.PackageNotFoundError:pass
    record={'name':args.name,'source_tree_sha256':before,'status':'PASS' if process.returncode==0 else 'FAIL','command':command,
            'environment':{'system':platform.system(),'release':platform.release(),'machine':platform.machine()},'versions':versions,
            'exit_code':process.returncode,'log':log.name,'summary':summaries[-1].strip() if summaries else 'Command completed; semantic assertion is documented in acceptance report.',
            'gaps':[] if process.returncode==0 else ['command failed; inspect captured log']}
    (args.evidence/(args.name+'.json')).write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record));sys.exit(process.returncode)
if __name__=='__main__':main()
