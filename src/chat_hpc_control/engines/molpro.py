from .native import NativeEngine

def create_plugin():
    return NativeEngine('molpro',('raw-only','molpro-table-v1','molpro-xml-single-v1'))
