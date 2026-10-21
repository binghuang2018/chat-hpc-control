from copy import deepcopy
from chat_hpc_control.clients import openai,anthropic,gemini
MODULES={'openai':openai,'anthropic':anthropic,'gemini':gemini}


def wire(name,calls=None,text='done'):
    calls=calls or []
    if name=='openai':
        import json
        output=[{'type':'function_call','call_id':str(i),'name':n,'arguments':json.dumps(a)} for i,(n,a) in enumerate(calls)]
        if not calls:output=[{'type':'message','content':[{'type':'output_text','text':text}]}]
        return {'id':'synthetic','status':'completed','output':output}
    if name=='anthropic':
        return {'id':'synthetic','stop_reason':'tool_use' if calls else 'end_turn','content':
          [{'type':'tool_use','id':str(i),'name':n,'input':a} for i,(n,a) in enumerate(calls)] if calls else [{'type':'text','text':text}]}
    return {'id':'synthetic','status':'requires_action' if calls else 'completed','steps':
          [{'type':'function_call','id':str(i),'name':n,'arguments':a} for i,(n,a) in enumerate(calls)] if calls else
          [{'type':'model_output','content':[{'type':'text','text':text}]}]}


def fake_adapter(name,responses):
    adapter=MODULES[name].create_adapter()
    adapter.requests=[]
    pending=iter(responses)
    def request(items,previous_id=None):
        adapter.requests.append(deepcopy((items,previous_id)))
        item=next(pending)
        if isinstance(item,Exception):raise item
        return item
    adapter.request=request
    return adapter
