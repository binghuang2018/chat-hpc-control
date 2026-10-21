"""OpenAI Responses function calling, SDK imported only when connecting."""

import json
from .base import NativeClient,checked_call,object_data,unique_calls
from ..contracts.errors import ControlError
from ..core.service import tool_definitions


class OpenAIAdapter(NativeClient):
    provider='openai'
    def tool_definitions(self):
        return [{'type':'function','name':t['name'],'description':t['description'],
                 'parameters':t['inputSchema'],'strict':False} for t in tool_definitions()]

    def decode_calls(self,response):
        data=object_data(response)
        if data.get('status')!='completed':raise ControlError('SCHEMA_INVALID','incomplete OpenAI response cannot execute tools')
        calls=[]
        for item in data.get('output',[]):
            if item.get('type')=='function_call':
                if item.get('status','completed')!='completed':raise ControlError('SCHEMA_INVALID','partial function call')
                calls.append(checked_call(item.get('name'),item.get('arguments'),item.get('call_id')))
        return unique_calls(calls)

    def encode_result(self,call,result):
        return {'type':'function_call_output','call_id':call.provider_call_id,'output':json.dumps(result.to_dict(),allow_nan=False)}

    def connect(self,api_key):
        try:from openai import OpenAI
        except ImportError as exc:raise ControlError('CAPABILITY_UNSUPPORTED','install chat-hpc-control[openai]') from exc
        if not api_key:raise ControlError('AUTH_DENIED','explicit OpenAI API key is required')
        self.client=OpenAI(api_key=api_key,max_retries=0);return self

    def request(self,input_items,*,previous_id=None):
        self._configured()
        kwargs={'model':self.model,'input':input_items,'tools':self.tool_definitions(),
                'max_output_tokens':self.max_output_tokens,'stream':False}
        if previous_id:kwargs['previous_response_id']=previous_id
        return self.client.responses.create(**kwargs)

    def continuation(self,response,results):
        data=object_data(response)
        # Preserve every output item, including reasoning metadata, as required
        # by the Responses continuation protocol.
        return [*data.get('output',[]),*results],None

    def final_text(self,response):
        data=object_data(response)
        return ''.join(c.get('text','') for item in data.get('output',[]) if item.get('type')=='message'
                       for c in item.get('content',[]) if c.get('type')=='output_text')


def create_adapter(**kwargs):return OpenAIAdapter(**kwargs)
