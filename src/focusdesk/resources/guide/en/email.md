# Email and attachments {#e-mail-si-atasamente}
## Purpose {#la-ce-foloseste}
Compose a new editable task message with its full description, then send through Outlook Classic (default) or Gmail with an app password. No Reply/ReplyAll or inbox scanning. Editing the message does not edit the task.
## Where to find it {#unde-il-gasesti}
Use **Ctrl+M**, **Organize → Email from task…**, task **More → Compose email…**, or **Files → Attach to email…**.
## Tutorial H: full description and selected documents {#tutorial-h-descriere-completa-si-documente-alese}
1. With unsaved description edits, choose current description (default), last saved version or Cancel; this does not save task metadata.
2. Fill To, CC and Subject. Never use fictional tutorial addresses for real sending.
3. Edit Message; full text, line breaks and accents remain, without the old 600-character limit. Refresh does not regenerate it.
4. Select needed [attachments](#atasamente).
5. **Open draft in Outlook** for review, or **Send** and confirm recipients, subject, attachment count/size.
## Attachments {#atasamente}
Add files… supports multiple files. From task/project files… includes manually added documents. Remove from email changes selection only. Same names at different paths are distinct. Folders are not zipped/attached automatically; files are rechecked before handoff. A rejected attachment stops the operation without partial sending.
## Results and saving {#rezultate-si-salvare}
Opened draft is not sent. Submitted to Outlook means Send returned successfully, not delivery. Check Outlook Outbox/Sent Items. The task journal records result and attachment names, not the full body.
## Errors and mistakes {#erori-si-greseli-frecvente}
Enter in a field does not send. Errors retain the form. For timeout/uncertain result, check Outlook before **I checked in Outlook…** and explicit retry; no automatic retry. Journal failure does not justify resending. The form is not a persistent local draft after app exit. [Outlook](guide:setari#outlook-classic-si-lucru-offline).

## Gmail setup {#gmail-configurare}
Outlook Classic remains the default. Open **Settings → Integrations → Email**, or **Configure Gmail…** in the composer. Enter the Gmail/Google Workspace account address (custom domains are supported) and an optional display name. The composer does not offer arbitrary senders or unverified aliases.

Enable Two-Step Verification in your Google account and manually generate an app password in your browser at `https://myaccount.google.com/apppasswords`, using **How do I get an app password?**. Enter the masked app password in FocusDesk, not your regular password or verification codes. Only presentation spaces are removed. Organization policy, Advanced Protection or other account restrictions may prevent app passwords. Changing your Google password may revoke them. This is not OAuth or “Sign in with Google”.

**Remember securely on this computer** uses Windows Credential Manager. The secret is excluded from the workspace, JSON, journal and backups. Without secure storage, it stays in session memory only and must be re-entered after restart. **Save email settings** saves only this computer’s profile, not task edits. If an older credential cannot be deleted, a warning and its reference are retained for later removal.

**Test connection** checks TLS and authentication without sending a message or saving fields. Success does not guarantee message acceptance or delivery. **Remove credentials** deletes the local secret and account metadata; revoke the app password separately in your Google account.

## Gmail sending and results {#gmail-trimitere}
In the same composer choose **Send via → Gmail — account address**. Provider changes and configuration preserve To, CC, subject, body and attachments. The Outlook calendar is unchanged. Gmail needs no Outlook, but sending and connection tests need internet; the rest of FocusDesk remains offline.

**Send** asks you to confirm the account and message. SMTP uses `smtp.gmail.com:465`, verified TLS and timeouts, never an unencrypted connection. All selected documents are read before submission; missing or unreadable files block incomplete messages.

**Message accepted by Gmail’s server for sending** is not delivery or read confirmation. Partial acceptance lists accepted and refused recipients with SMTP codes. **Prepare refused recipients only…** removes already accepted recipients from the next attempt and requires a new confirmation. There is no automatic retry or Outlook fallback. A connection lost during submission leaves an uncertain result: check Gmail/recipients before **I checked Gmail…**. Switching providers alone never unlocks resending.

SMTP does not create drafts in Gmail web. **Save as .eml (local)…** creates a local file with body and attachments, without sending or synchronization. **Open draft in Outlook** is available only for Outlook. The journal records provider, account, recipients, subject, time, Message-ID and attachment names, never the secret or SMTP conversation. A failed journal write after acceptance is not a reason to resend.

Troubleshoot internet/DNS, timeout, TLS/certificates, authentication, recipients and account limits separately. Authentication codes cannot always distinguish an incorrect password, a revoked password and an account policy. Errors retain the form; never disable TLS security to bypass them.
