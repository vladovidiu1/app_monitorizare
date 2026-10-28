"""Capturi pe date temporare; necesită opțional Pillow și un display/Xvfb, fără Outlook real."""
import tempfile,os
from pathlib import Path
from datetime import timedelta
from PIL import ImageGrab
from focusdesk.domain.common import utcnow
from focusdesk.services.workspace import Workspace
from focusdesk.integrations.meetings import CalendarMeeting,MeetingBatch
from focusdesk.domain.models import Kind
with tempfile.TemporaryDirectory(prefix='focusdesk-meetings-demo-') as temp:
    root=Path(temp);os.environ['APPDATA']=str(root/'profile')
    ws=Workspace.open(root/'workspace',create=True,name='Întâlniri · demonstrație locală')
    svc=ws.meetings;svc.configure('demo-store','demo-calendar','Calendar demonstrativ · backend fals, fără Outlook real')
    now=utcnow().replace(second=0,microsecond=0)
    events=[CalendarMeeting(uid='weekly',occurrence_key=now.isoformat(),title='Actualizare raport lunar · decizii și acțiuni',start=now-timedelta(minutes=15),end=now+timedelta(minutes=45),location='Sala proiectului',organizer='Ana Popescu'),CalendarMeeting(uid='review',title='Revizie script și validare rezultate',start=now+timedelta(days=1),end=now+timedelta(days=1,hours=1),location='Online',organizer='Echipa operațională')]
    svc.import_batch('demo-store','demo-calendar',MeetingBatch(events),now-timedelta(days=14),now+timedelta(days=60))
    mid=next(r['id'] for r in svc.store.summaries() if r['title'].startswith('Actualizare'))
    svc.save_notes(mid,'Subiecte discutate\n\nRaportul trebuie să includă diferențele dintre versiunile scriptului.\nSe păstrează compatibilitatea cu fișierele existente.\n\nDecizii\n\nValidăm întâi pe date demonstrative. Nu schimbăm automat datele de producție.\n\nDe clarificat\n\nCine confirmă rezultatul înainte de utilizarea zilnică?')
    action=svc.save_action(mid,text='Adaugă verificarea diferențelor în raport',responsible='Eu',state='todo')
    svc.save_action(mid,text='Confirmă setul de date pentru validare',responsible='Ana Popescu',state='clarify')
    svc.create_node(mid,request_id=__import__('uuid').uuid4().__str__(),title='Verificarea diferențelor în raport',description='Fragment ales explicit din discuție.',action_id=action.id)
    ws.close()
    from focusdesk.ui.app import FocusDeskApp
    app=FocusDeskApp();app._post_open_checks=lambda:None
    app.open_workspace(root/'workspace');app.root.geometry('1320x900+0+0')
    app.show_view('calendar');page=app.calendar_page.meetings;app.calendar_page.nb.select(page);app.root.update()
    def shot(name):
        app.root.update();r=app.root
        ImageGrab.grab(bbox=(r.winfo_rootx(),r.winfo_rooty(),r.winfo_rootx()+r.winfo_width(),r.winfo_rooty()+r.winfo_height())).save('docs/capturi-ui/'+name)
    shot('intalniri-lista.png')
    page.open(mid);app.root.update();shot('intalnire-notite.png')
    page.back();app._release_current();app.root.destroy()
