"""Google GenAI Interactions function calls and explicit continuation IDs."""

import json
from .base import NativeClient,checked_call,object_data,unique_calls
from ..contracts.errors import ControlError
from ..core.service import tool_definitions


class GeminiAdapter(NativeClient):
    provider='gemini'
    def tool_definitions(self):
        return [{'type':'function','name':t['name'],'description':t['description'],'parameters':t['inputSchema']} for t in tool_definitions()]

    def decode_calls(self,response):
        data=object_data(response)
        if data.get('status') not in {'completed','requires_action'}:
            raise ControlError('SCHEMA_INVALID','incomplete Gemini interaction cannot execute tools')
        return unique_calls([checked_call(item.get('name'),item.get('arguments'),item.get('id'))
                             for item in data.get('steps',[]) if item.get('type')=='function_call'])

    def encode_result(self,call,result):
        return {'type':'function_result','name':call.name,'call_id':call.provider_call_id,
                'result':[{'type':'text','text':json.dumps(result.to_dict(),allow_nan=False)}]}

    def connect(self,api_key):
        try:from google import genai
        # Retry policy is explicit; a client turn owns the API attempt budget.
        # The calculation intent remains durable even if a request is uncertain.
        except ImportError as exc:raise ControlError('CAPABILITY_UNSUPPORTED','install chat-hpc-control[gemini]') from exc
        if not api_key:raise ControlError('AUTH_DENIED','explicit Gemini API key is required')
        self.client=genai.Client(api_key=api_key,http_options={"retry_options":{"attempts":1}});return self

    def request(self,input_items,*,previous_id=None):
        self._configured()
        kwargs={'model':self.model,'input':input_items,'tools':self.tool_definitions(),'stream':False,
                'generation_config':{'max_output_tokens':self.max_output_tokens}}
        if previous_id:kwargs['previous_interaction_id']=previous_id
        return self.client.interactions.create(**kwargs)

    def continuation(self,response,results):
        data=object_data(response)
        if not data.get('id'):raise ControlError('SCHEMA_INVALID','Gemini continuation requires interaction identity')
        return results,data['id']

    def final_text(self,response):
        return ''.join(block.get('text','') for step in object_data(response).get('steps',[])
                       if step.get('type')=='model_output' for block in step.get('content',[]) if block.get('type')=='text')


def create_adapter(**kwargs):return GeminiAdapter(**kwargs)
