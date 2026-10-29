# Troubleshooting and limitations {#probleme-frecvente-si-limitari}
## Cannot find a completed task {#nu-gasesc-un-task-finalizat}
Use Completed/Closed and matching filters; also check Archive. Project links do not change membership. [Reopen and new requirement](guide:cerinte) serve different purposes.
## Description was not kept {#descrierea-nu-s-a-pastrat}
Applying the description guide changes the draft; Save/Ctrl+S persists it. Cancelling the expanded editor restores its opening snapshot. Task journal notes need explicit addition; [meeting notes](guide:intalniri) autosave.
## A new document is missing {#un-document-nou-nu-apare}
Check the actual Files root, expand the folder and Refresh/F5. Inaccessible folders may show older listings; this does not prove current availability. Links/junctions are not traversed automatically. [Files](guide:fisiere).
## Scheduled is higher than worked {#vad-programat-dar-nu-am-lucrat-atat}
Bookings are not work. Saved actual duration and live time are separate; meetings add no work. Check report filters and correct only identifiable finished sessions. [Calculation rules](guide:activitate).
## Outlook does not respond or a module is missing {#outlook-nu-raspunde-sau-lipseste-un-modul}
Use Outlook Classic, respect company policy. `ModuleNotFoundError: win32timezone` means missing pywin32 components; a frozen executable needs rebuilding with them, not merely installing Python packages elsewhere. After Send timeout check Outlook windows, Drafts, Outbox and Sent Items before retrying. A successful COM call is not delivery. [Email errors](guide:email#erori-si-greseli-frecvente).
## Save refused or external changes {#salvare-refuzata-sau-modificari-externe}
Protect important drafts. F5 preserves conflict checks; do not overwrite authoritative files blindly. Read-only can result from another process’s lock. **Check workspace integrity…** reports issues without automatically deleting data.
## Performance and safety limits {#limite-de-performanta-si-siguranta}
Initial index rebuilding/global description search can read more data. Files explores expanded directories only; guide search reads bundled documentation only. Indexes are disposable, but no substitute for backups. No SQL/SQLite or cloud data sync.
## Check on your own computer {#ce-trebuie-verificat-pe-calculatorul-tau}
Real Outlook/COM policy, document associations, VS Code, junctions, native DPI and Windows executables depend on the target environment. Fake-backend and Linux scaling tests do not certify them. Blocked network system calls cannot safely be forcibly cancelled. Test restores on temporary data; back up external folders separately.
