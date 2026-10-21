import sys
from pathlib import Path


def main():
    from chat_hpc_control.core.broker import Broker
    from chat_hpc_control.core.config import load_site
    from chat_hpc_control.core.rpc import serve
    from chat_hpc_control.core.service import ToolService
    from chat_hpc_control.core.store import StateStore
    from chat_hpc_control.sources.base import SourceResolver
    from chat_hpc_control.contracts.errors import ControlError
    from tests.fakes import DemoEngine, RecordingExecutor
    try:
        site = load_site(Path(sys.argv[1]))
        store = StateStore.open(site.root)
        serve(site, ToolService(Broker(site, store, SourceResolver(), {"demo": DemoEngine()}, RecordingExecutor())))
    except ControlError as exc:
        print(exc.code, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
