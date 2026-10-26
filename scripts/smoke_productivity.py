"""Smoke opțional GGUF real: ciornă, selecție pentru Planner, raport; fără aplicare/Outlook."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import multiprocessing
from pathlib import Path
import queue
import sys
import tempfile
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))


def main():
    from focusdesk.ai.models import default_model_path
    from focusdesk.ai.process import EngineProcess
    from focusdesk.ai.protocol import EngineSettings, Request
    from focusdesk.domain.models import Kind
    from focusdesk.domain.session import SessionRecord
    from focusdesk.services.ai_productivity import (MAIL_MODES, DAY_INSTRUCTION, REPORT_INSTRUCTION,
        day_context, day_selection, mail_instruction, report_context, validate_mail_reply)
    from focusdesk.services.assistant_context import build_context
    from focusdesk.services.assistant_proposals import ProposalBatch
    from focusdesk.services.queries import Queries
    from focusdesk.services.workspace import Workspace
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, default=default_model_path())
    parser.add_argument('--mode', choices=['mail','day','report','all'], default='all')
    parser.add_argument('--timeout', type=int, default=300)
    args = parser.parse_args()
    callbacks = queue.Queue()
    engine = EngineProcess(EngineSettings(model_path=str(args.model), timeout=args.timeout), callbacks.put)
    try:
        with tempfile.TemporaryDirectory(prefix='focusdesk-productivity-') as directory:
            ws = Workspace.open(Path(directory)/'data',create=True)
            try:
                now = datetime.now(timezone.utc)
                task = ws.create_node(Kind.TASK,'Validare raport',estimated_minutes=30,next_action='Cere clarificarea datelor lipsă')
                ws.add_note(task.id,'Datele sunt incomplete. Solicită clarificări înainte de continuare.')
                ws.repo.sessions.save(SessionRecord(node_id=task.id,start_at=now-timedelta(hours=1),end_at=now-timedelta(minutes=30),actual_seconds=600,status='done'))
                modes = ['mail','day','report'] if args.mode == 'all' else [args.mode]
                for mode in modes:
                    if mode == 'mail':
                        question=mail_instruction(ws,task.id,MAIL_MODES[1])
                        bundle=build_context(ws,'task',task.id,question)
                    elif mode == 'day':
                        question=DAY_INSTRUCTION+'Alege o singură prioritate.'
                        bundle=day_context(ws,'')
                    else:
                        question=REPORT_INSTRUCTION
                        bundle,_=report_context(ws,Queries(ws).today(),Queries(ws).today())
                    results=[]
                    engine.submit(Request(request_id=str(uuid4()),action='assistant',intent='email' if mode=='mail' else 'chat',instruction=question,context=bundle.wire()),results.append)
                    while not results or results[-1].kind == 'loading':
                        callbacks.get(timeout=args.timeout+5)()
                    response=results[-1]
                    if response.kind!='result':
                        raise RuntimeError(response.error)
                    if mode=='mail':
                        validate_mail_reply(ws,bundle,response.assistant,response.context_keys,task.id)
                    elif mode=='day':
                        day_selection(ws,bundle,response.assistant,response.context_keys)
                    else:
                        ProposalBatch.prepare(ws,bundle,response.assistant,response.context_keys,'chat')
                    assert len(ws.nodes)==1 and len(ws.list_notes(task.id))==1 and len(ws.repo.sessions.list_all())==1
                    print(json.dumps({'status':'ok','mode':mode,'inference':'REAL GGUF CPU','usage':response.usage,'sources':len(response.context_keys),'actions_applied':0,'messages_sent':0}),flush=True)
            finally:
                ws.close()
    finally:
        engine.close()
        if not engine.wait_closed():
            raise RuntimeError('Procesul AI nu s-a oprit.')
    return 0


if __name__ == '__main__':
    multiprocessing.freeze_support()
    raise SystemExit(main())
