from .native import NativeEngine

def create_plugin():
    return NativeEngine('pyscf',('pyscf-json-v1','raw-only'))
