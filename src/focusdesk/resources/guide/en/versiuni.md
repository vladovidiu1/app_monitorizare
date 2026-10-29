# Versions, checkpoints and code {#versiuni-checkpointuri-si-acces-la-cod}
## Purpose {#la-ce-foloseste}
A checkpoint is a local snapshot of eligible saved code-folder files for comparison/restoration. Git is separate and optional; scripts are not executed.
## Where to find it {#unde-il-gasesti}
Task **Versions**; associate code in [Files](guide:fisiere), exclusions/limits in **Settings → Versions & VS Code**.
## Making a checkpoint {#pasi-pentru-un-checkpoint}
1. Save files in your external editor.
2. Check the own/inherited/shared code root.
3. Enter checkpoint description and **Save checkpoint**.
4. Use Included files…, Compare with current/previous.
5. Prefer **Restore to separate folder…** outside active source.
## Result and saving {#rezultatul-si-salvarea}
Archive/manifest obey exclusions and limits; unchanged content may produce no new copy. Separate restoration leaves current source unchanged. Overwrite source… is a distinct confirmed action with safeguards.
## Automation and Git {#automatizari-si-git}
Session-end/daily checkpoints require configuration and a valid source. Scheduling runs only while FocusDesk runs. Git supports status/log/diff and explicit commits for selected files; no automatic push/reset/checkout.
## Common mistakes {#greseli-frecvente}
A checkpoint is not a whole-workspace backup. External associations do not change backup rules. Keep each [requirement’s](guide:cerinte#folder-de-cod-comun) versions and own work distinct.
