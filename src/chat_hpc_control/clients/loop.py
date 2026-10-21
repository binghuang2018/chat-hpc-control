"""Complete-response loop; client budgets never become calculation walltimes."""

from copy import deepcopy
from ..contracts.errors import ControlError
from ..contracts.tools import ToolCall,ToolResponse
from ..core.manifest import canonical_bytes
from .base import object_data


def run_turn(adapter,session,user_request,dispatch,*,max_rounds=4,max_calls=16):
    if type(max_rounds)!=int or type(max_calls)!=int or not 1<=max_rounds<=128 or not 1<=max_calls<=128:
        raise ControlError('SCHEMA_INVALID','client API round/call budgets must be explicit positive bounded integers')
    request=session.current(user_request);request_id=request['id'];provider=adapter.provider
    initial=user_request if provider=='gemini' else [{'role':'user','content':user_request}]
    conversation=session.conversation(request_id,provider,initial)
    history,previous,pending=conversation['history'],conversation['previous_id'],conversation['pending']
    calls_used=0
    def summary(state,**extra):
        current=session.current(user_request)
        return {'state':state,'state_kind':'client','client_request_id':request_id,'run_ids':[current['run_id']] if current['run_id'] else [],
                'idempotency_key':current['intent_key'],**extra}
    try:
        for _ in range(max_rounds):
            if pending is None:
                # Save the exact continuation before making a possibly uncertain
                # network request. A retry uses the same human intent ledger.
                session.save_conversation(request_id,provider,history,previous)
                pending=object_data(adapter.request(history,previous_id=previous))
                session.save_conversation(request_id,provider,history,previous,pending)
            calls=adapter.decode_calls(pending)  # validate the whole batch first
            if not calls:
                text=adapter.final_text(pending)
                session.save_conversation(request_id,provider,history,previous)
                return summary('COMPLETED',text=text)
            if calls_used+len(calls)>max_calls:return summary('CLIENT_BUDGET_REACHED')
            results=[]
            for call in calls:
                if call.arguments.get('site_id')!=request['site_id']:
                    raise ControlError('AUTH_DENIED','model call targets another client site')
                effective=call
                if call.name=='submit_task':
                    args=deepcopy(call.arguments);digest=args['expected_manifest_sha256']
                    approved=session.approved_task(request_id,digest)
                    if canonical_bytes(approved)!=canonical_bytes(args['task']):
                        raise ControlError('INPUT_CHANGED','model submit differs from saved validated task')
                    if args['rerun_of']!=request['rerun_of']:
                        raise ControlError('AUTH_DENIED','only the explicit human request may authorize a rerun')
                    args['idempotency_key']=session.reserve_intent(request_id,'primary',digest)
                    effective=ToolCall(call.name,args,call.provider_call_id)
                fingerprint,saved=session.saved_call(request_id,provider,effective)
                if saved is not None:response=ToolResponse(**saved)
                else:
                    if call.name=='submit_task':session.mark_attempted(request_id)
                    response=dispatch(effective)
                    if not isinstance(response,ToolResponse):raise ControlError('SCHEMA_INVALID','dispatch returned no complete tool response')
                    if response.ok and call.name=='validate_task':session.pin_validation(request_id,response.data)
                    if response.ok and call.name=='submit_task':session.record_run(request_id,response.data['run_id'])
                    session.save_call(request_id,provider,effective,fingerprint,response)
                results.append(adapter.encode_result(call,response));calls_used+=1
            more,new_previous=adapter.continuation(pending,results)
            if new_previous is not None:history,previous=more,new_previous
            else:history=[*history,*more]
            pending=None
            session.save_conversation(request_id,provider,history,previous)
        return summary('CLIENT_BUDGET_REACHED')
    except ControlError as exc:
        session.save_conversation(request_id,provider,history,previous)
        return summary('REFUSED',error=exc.to_dict())
    except Exception:
        # No new key, automatic rerun, cancellation or unbudgeted API retry.
        return summary('CLIENT_REQUEST_UNKNOWN',error={'code':'CLIENT_REQUEST_UNKNOWN',
                       'message':'resume the same explicit client request; no new calculation intent was created'})
