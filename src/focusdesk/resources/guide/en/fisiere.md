# Files and the project folder {#fisiere-si-folderul-proiectului}
## Purpose {#la-ce-foloseste}
Explore actual disk folders, including documents added manually. Navigation does not edit node metadata or require registering every document.
## Where to find it {#unde-il-gasesti}
Task **Files** shows Project/working folder, Task files (files/) and External links/other references. Inherited roots name their source; overlaps do not create copies.
## Tutorial G: associate a folder and discover a document {#tutorial-g-folder-asociat-si-document-pus-manual}
1. Select your SAP project, **Files → Actions → Choose project folder…**.
2. Choose an existing folder; this neither moves nor copies it.
3. Select a project task and check “Inherited from”.
4. Expand Documents; closed subfolders are not recursively scanned.
5. Add a document using Explorer, then return or use Refresh/F5 inside Files.
6. Enter/double-click opens safe documents; **Attach to email…** preselects them in the email form.
## Result and saving {#rezultatul-si-salvarea}
New documents appear without node.json changes. Refresh preserves expanded-folder context; **Load next 200** extends large listings. **More space for Files** widens the task panel.
## Copies, references and safety {#copii-referinte-si-siguranta}
Add… offers a managed copy or external link. Managed files enter full backups; external links save only paths. Removing a reference does not delete its original, which can remain visible on disk. Deleting a managed copy is distinct and confirmed. Existing references can be relocated. Scripts/executables require VS Code/Explorer instead of accidental execution. Symlinks/junctions are not automatically traversed. Slow/unavailable network folders do not justify deleting data. [Backup](guide:siguranta).
