from .native import NativeEngine

def create_plugin():
    return NativeEngine('orca',('raw-only','orca-single-v1','orca-engrad-v1'))
