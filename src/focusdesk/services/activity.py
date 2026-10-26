"""Activity ledger: direct saved seconds, never rolled-up task totals."""
from datetime import timedelta


def activity_ledger(ws, days=30):
    from .queries import Queries
    q = Queries(ws)
    today = q.today()
    first = today - timedelta(days=days-1) if days else None
    daily, projects, sessions = {}, {}, []
    def bucket(mapping, key):
        return mapping.setdefault(key, {'worked': 0, 'planned': 0})
    for s in ws.repo.sessions.list_all():
        node = ws.nodes.get(s.node_id)
        project = ws.nearest_project(node.id) if node else None
        pid = project.id if project else None
        when = (s.started_actual_at or s.start_at).astimezone(q.tz()).date()
        planned_day = s.start_at.astimezone(q.tz()).date()
        worked_in = not first or first <= when <= today
        planned_in = not first or first <= planned_day <= today
        if not (worked_in or planned_in):
            continue
        worked = max(0, s.actual_seconds) if worked_in else 0
        planned = s.planned_minutes * 60 if planned_in and s.status not in ('cancelled','missed') else 0
        if worked:
            bucket(daily, when)['worked'] += worked
        if planned:
            bucket(daily, planned_day)['planned'] += planned
        p = bucket(projects, pid)
        p.update(name=project.title if project else 'Fără proiect')
        p['worked'] += worked
        p['planned'] += planned
        sessions.append((s, node, p['name']))
    return {'days': daily, 'projects': projects, 'sessions': sorted(sessions,key=lambda r:r[0].start_at,reverse=True),
            'worked': sum(v['worked'] for v in daily.values()), 'planned': sum(v['planned'] for v in daily.values())}
