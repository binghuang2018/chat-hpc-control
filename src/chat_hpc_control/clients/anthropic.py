"""Anthropic Messages client tools; original thinking blocks stay in history."""

import json
from .base import NativeClient,checked_call,object_data,unique_calls
from ..contracts.errors import ControlError
from ..core.service import tool_definitions


class AnthropicAdapter(NativeClient):
    provider='anthropic'
    def tool_definitions(self):
        return [{'name':t['name'],'description':t['description'],'input_schema':t['inputSchema']} for t in tool_definitions()]

    def decode_calls(self,response):
        data=object_data(response)
        if data.get('stop_reason') not in {'tool_use','end_turn','stop_sequence'}:
            raise ControlError('SCHEMA_INVALID','incomplete Anthropic message cannot execute tools')
        return unique_calls([checked_call(item.get('name'),item.get('input'),item.get('id'))
                             for item in data.get('content',[]) if item.get('type')=='tool_use'])

    def encode_result(self,call,result):
        return {'type':'tool_result','tool_use_id':call.provider_call_id,'content':json.dumps(result.to_dict(),allow_nan=False),
                'is_error':not result.ok}

    def connect(self,api_key):
        try:from anthropic import Anthropic
        except ImportError as exc:raise ControlError('CAPABILITY_UNSUPPORTED','install chat-hpc-control[anthropic]') from exc
        if not api_key:raise ControlError('AUTH_DENIED','explicit Anthropic API key is required')
        self.client=Anthropic(api_key=api_key,max_retries=0);return self

    def request(self,input_items,*,previous_id=None):
        self._configured()
        return self.client.messages.create(model=self.model,messages=input_items,tools=self.tool_definitions(),
                    max_tokens=self.max_output_tokens,stream=False)

    def continuation(self,response,results):
        data=object_data(response)
        return [{'role':'assistant','content':data['content']},{'role':'user','content':results}],None

    def final_text(self,response):
        return ''.join(item.get('text','') for item in object_data(response).get('content',[]) if item.get('type')=='text')


def create_adapter(**kwargs):return AnthropicAdapter(**kwargs)
