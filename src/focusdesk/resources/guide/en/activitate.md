# Understanding Activity {#activitate-intelegerea-dashboardului}
## Purpose {#la-ce-foloseste}
The dashboard, monthly calendar, tables and CSV use one calculation model, without counting parent/subtask work twice.
## Where to find it {#unde-il-gasesti}
Choose **Activity**; **Monthly calendar · Ctrl+D** opens the secondary calendar.
## Tutorial J: check recorded work {#tutorial-j-verifica-timpul-lucrat}
1. Choose 7/30/90 days, Current month, Custom range or All history.
2. Select a project or No project; apply custom dates explicitly.
3. Compare Recorded work with Scheduled; do not add them as work.
4. Select a chart day/project; **Clear detail** removes that filter, **Reset filters** resets all.
5. Enter/double-click a session opens its task; returning keeps context.
6. **Export CSV** respects filters and includes definitions, accents and Excel formula protection.
## Reading the cards {#cum-interpretezi-cardurile}
Recorded work sums saved actual_seconds once per session, including completed/archived/missing tasks. Its day is actual start (fallback scheduled start) in workspace time zone. Live unsaved time is separate. Scheduled means eligible reservations, excluding cancelled/missed. Imported meetings affect neither total.
Completed counts distinct tasks transitioning to done in the period; reopening/refinishing does not duplicate a task. Old missing history cannot be invented from updated_at. Overdue now and status distribution describe current state. Projects reflect current membership. Long periods aggregate by weeks/months, as labelled.
## Saving and common mistakes {#salvare-si-greseli-frecvente}
Filters do not change sessions. Export explicitly writes the selected file. Correct only identifiable finished sessions, then recheck totals. Hours alone are no productivity score. [Sessions](guide:sesiuni).
