"""Shared complete-message validation, with no automatic tool execution."""

import json
from typing import Protocol
from jsonschema import Draft202012Validator
from ..contracts.codec import check_json_tree,decode_json,parse_task
from ..contracts.errors import ControlError
from ..contracts.tools import ToolCall
from ..core.service import tool_definitions


def object_data(value):
    if hasattr(value,'model_dump'):value=value.model_dump(mode='json',exclude_none=True)
    if not isinstance(value,dict):raise ControlError('SCHEMA_INVALID','expected a complete provider response object')
    check_json_tree(value)
    if len(json.dumps(value,allow_nan=False).encode())>16*1024*1024:
        raise ControlError('SCHEMA_INVALID','provider response exceeds client byte budget')
    return value


def checked_call(name,arguments,call_id):
    definitions={t['name']:t for t in tool_definitions()}
    if not isinstance(name,str) or name not in definitions or not isinstance(call_id,str) or not 0<len(call_id)<=512:
        raise ControlError('SCHEMA_INVALID','unknown tool or invalid provider call ID')
    if isinstance(arguments,str):arguments=decode_json(arguments.encode())
    if not isinstance(arguments,dict):raise ControlError('SCHEMA_INVALID','tool arguments must be a complete JSON object')
    check_json_tree(arguments)
    if next(Draft202012Validator(definitions[name]['inputSchema']).iter_errors(arguments),None):
        raise ControlError('SCHEMA_INVALID','provider arguments violate the shared tool schema')
    if 'task' in arguments:parse_task(json.dumps(arguments['task']).encode())
    return ToolCall(name,arguments,call_id)


def unique_calls(calls):
    ids=[call.provider_call_id for call in calls]
    if len(ids)!=len(set(ids)):raise ControlError('SCHEMA_INVALID','duplicate provider call ID')
    return calls


class ProviderAdapter(Protocol):
    def tool_definitions(self):...
    def decode_calls(self,response):...
    def encode_result(self,call,result):...


class NativeClient:
    def __init__(self,*,client=None,model=None,max_output_tokens=2048):
        self.client,self.model,self.max_output_tokens=client,model,max_output_tokens

    def _configured(self):
        if self.client is None or not isinstance(self.model,str) or not self.model:
            raise ControlError('SCHEMA_INVALID','an explicit provider client and model are required')
        if type(self.max_output_tokens)!=int or not 1<=self.max_output_tokens<=100000:
            raise ControlError('SCHEMA_INVALID','invalid API output-token budget')
