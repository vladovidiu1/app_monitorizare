"""Reconcile stable Treeview rows on the Tk thread, in cancellable small batches."""

def sync_rows(tree, rows, *, batch=200):
    """Rows are fully filtered/sorted before this function; parents precede children."""
    pending = getattr(tree, '_rows_job', None)
    if pending:
        tree.after_cancel(pending)
        tree._rows_job = None
    generation = getattr(tree, '_rows_generation', 0) + 1
    tree._rows_generation = generation
    known = getattr(tree, '_rows_known', set())
    def collect(parent=''):
        for iid in tree.get_children(parent):
            known.add(iid); collect(iid)
    collect()
    tree._rows_known = known
    desired = {iid for parent,iid,options in rows}
    removed = [iid for iid in known-desired if tree.exists(iid)]
    if removed: tree.detach(*removed)
    # Existing selected rows remain on screen early in progressive fills.
    indices = {}
    positioned = []
    for parent, iid, options in rows:
        index = indices.get(parent,0); indices[parent] = index+1
        positioned.append((parent,iid,index,options))
    def apply(offset=0):
        if generation != tree._rows_generation: return
        tree._rows_job = None
        for parent,iid,index,options in positioned[offset:offset+batch]:
            if tree.exists(iid):
                old = tree.item(iid)
                patch = {}
                for key,value in options.items():
                    previous = old[key]
                    equal = bool(previous) == value if isinstance(value,bool) else (tuple(map(str,previous)) == tuple(map(str,value)) if isinstance(value,(tuple,list)) else str(previous) == str(value))
                    if not equal: patch[key] = value
                if patch: tree.item(iid,**patch)
                if tree.parent(iid) != parent or tree.index(iid) != index:
                    tree.move(iid,parent,index)
            else:
                tree.insert(parent,index,iid=iid,**options); known.add(iid)
        end = offset + batch
        if end < len(positioned):
            tree._rows_job = tree.after(1,lambda:apply(end))
        else:
            for iid in known-desired:
                if tree.exists(iid): tree.delete(iid)
            known.intersection_update(desired)
    apply()
