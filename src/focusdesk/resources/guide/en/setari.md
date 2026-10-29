# Settings and integrations {#setari-si-integrari}
## Purpose {#la-ce-foloseste}
Configure work conditions and optional integrations; local functions require neither Outlook nor cloud accounts.
## Where to find it {#unde-il-gasesti}
**Settings** or **Tools → Settings…**: General, Colleagues, Work schedule, Backup, Versions & VS Code, Outlook.
## Configuration steps {#pasi-pentru-configurare}
1. In General check name, time zone and daily priority limit.
2. **Language** lists Română, English, Deutsch, Français, Español. Apply language on restart saves the profile only; restart manually when ready. Drafts and timer are not touched.
3. Check working days, intervals, breaks and exceptions; they influence planning, not automatic work.
4. Configure reachable backup/code locations and Save.
## Colleagues and requester {#colegi-si-solicitant}
Load colleague Excel file… reads a local .xlsx, first sheet: name column A, code B. Codes omit the domain; the picker uses existing address conventions. Import replaces the list immediately, separately from Settings Save; invalid imports keep the old list. Task requester selection still needs task saving.
## Outlook Classic and offline work {#outlook-classic-si-lucru-offline}
COM needs Outlook Classic and packaged pywin32; New Outlook does not support it. Meeting import is read-only metadata, with local notes. Booking calendar and meeting source are separate choices. Email sending is explicit. Successful local Save/Send does not prove Exchange sync/delivery; ICS needs import. Without Outlook, local tasks, timer, reports, notes and manual meetings remain available. No hidden cloud backend.
## Common mistakes {#greseli-frecvente}
Language and workspace time zone are independent. Display dates are day-first; use YYYY-MM-DD for unambiguous input. ISO persistence never changes with language. Do not change time zone to repair totals. [Errors](guide:probleme).
