"""Local transactional checkpoints. Unknown in-flight work is never replayed."""
import json
import re
import sqlite3
import time
from pathlib import Path
from uuid import uuid4


class StateError(RuntimeError):
    pass


class RunStore:
    def __init__(self, root):
        self.root = Path(root)
        if any(p.is_symlink() or p.exists() and getattr(p.lstat(),'st_file_attributes',0)&0x400
               for p in (self.root,*self.root.parents)):
            raise StateError('Run storage cannot be a symlink')
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.db = self.root/'runs.sqlite3'
        if self.db.is_symlink():
            raise StateError('Run database cannot be a symlink')
        try:
            with self.connect() as c:
                c.execute('CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, revision INTEGER, data TEXT)')
        except sqlite3.Error as exc:
            raise StateError('Corrupt or inaccessible run database') from exc

    def connect(self):
        try:
            c = sqlite3.connect(self.db, timeout=10)
            c.execute('PRAGMA synchronous=FULL')
            return c
        except sqlite3.Error as exc:
            raise StateError('Cannot open run database') from exc

    @staticmethod
    def validate_id(identifier):
        if not isinstance(identifier,str) or not re.fullmatch(r'[0-9a-f]{32}',identifier):
            raise StateError('Invalid run ID')

    def create(self, data):
        identifier = uuid4().hex
        value = {**data,'run_id':identifier,'schema_version':1,'revision':0,'created_at':time.time()}
        with self.connect() as c:
            c.execute('INSERT INTO runs VALUES (?,0,?)',(identifier,json.dumps(value)))
        self.path(identifier).mkdir(mode=0o700)
        return value

    def path(self, identifier):
        self.validate_id(identifier)
        path = self.root/identifier
        if path.is_symlink() or path.exists() and getattr(path.lstat(),'st_file_attributes',0)&0x400:
            raise StateError('Run directory cannot be a symlink')
        return path

    def read(self, identifier):
        self.validate_id(identifier)
        try:
            with self.connect() as c:
                row=c.execute('SELECT data FROM runs WHERE id=?',(identifier,)).fetchone()
            if row is None or len(row[0]) > 8_000_000:
                raise StateError('Run not found or checkpoint exceeds size bound')
            data=json.loads(row[0])
            if data.get('schema_version') != 1 or data.get('run_id') != identifier:
                raise StateError('Incompatible checkpoint schema')
            return data
        except (sqlite3.Error,ValueError,TypeError) as exc:
            raise StateError('Corrupt run checkpoint') from exc

    def update(self, identifier, revision, changes):
        data=self.read(identifier)
        data.update(changes)
        data['revision']=revision+1
        encoded=json.dumps(data)
        if len(encoded) > 8_000_000:
            raise StateError('Checkpoint exceeds size bound')
        with self.connect() as c:
            cursor=c.execute('UPDATE runs SET revision=?,data=? WHERE id=? AND revision=?',
                             (revision+1,encoded,identifier,revision))
            if cursor.rowcount != 1:
                raise StateError('Concurrent or stale checkpoint writer')
        return data

    def cancel(self, identifier):
        data=self.read(identifier)
        return self.update(identifier,data['revision'],{'cancel_requested':True})

    def reconcile(self, identifier, request_id, amount, reference):
        """Explicit user-provided invoice reconciliation, not provider certification."""
        from .ledger import BudgetLedger, money
        if not isinstance(reference,str) or not reference.strip() or len(reference)>500:
            raise StateError('A bounded billing reference is required')
        data=self.read(identifier)
        if data.get('phase')!='completed':
            raise StateError('Stop execution before reconciling billing')
        accounting=data['accounting']
        ledger=BudgetLedger.restore(accounting['ledger_checkpoint']) if accounting.get('ledger_checkpoint') else None
        if ledger:
            ledger.reconcile(request_id,amount)
        found=False
        for observation in accounting['observations']:
            if observation['request_id']==request_id:
                if observation.get('billing_reference') not in (None,reference):
                    raise StateError('Conflicting billing reference')
                observation.update(billed_cost_usd=str(money(amount)),
                    billing_origin='user_reconciled_invoice',billing_reference=reference)
                found=True
        if not found:
            raise StateError('Billing request not present in observations')
        accounting.update(ledger=ledger.snapshot() if ledger else None,ledger_checkpoint=ledger.checkpoint() if ledger else None,
            budget_verdict='reconciled' if all(o['billed_cost_usd'] is not None for o in accounting['observations']) else 'unknown')
        result=data.get('result',{})
        result.update(accounting=accounting,budget_verdict=accounting['budget_verdict'])
        return self.update(identifier,data['revision'],{'accounting':accounting,'result':result})

    def prune(self, *, older_than_days=30, apply=False):
        """Explicit retention; completed runs only. Uncertain runs are retained."""
        import shutil
        if type(older_than_days) is not int or older_than_days<0:
            raise StateError('Retention days must be a nonnegative integer')
        cutoff=time.time()-older_than_days*86400
        with self.connect() as c:
            ids=[row[0] for row in c.execute('SELECT id FROM runs')]
        selected=[]
        for identifier in ids:
            state=self.read(identifier)
            if state.get('phase')!='completed' or state.get('created_at',time.time())>cutoff:
                continue
            accounting=state.get('accounting',{})
            if accounting.get('pending_requests'):
                continue
            path=self.path(identifier)
            if path.exists() and getattr(path.lstat(),'st_file_attributes',0)&0x400:
                raise StateError('Refuse deleting a reparse point')
            selected.append(identifier)
            if apply:
                self.update(identifier,state['revision'],{'phase':'pruning'})
                if path.exists():
                    shutil.rmtree(path)
                with self.connect() as c:
                    c.execute('DELETE FROM runs WHERE id=?',(identifier,))
        return {'run_ids':selected,'deleted':apply,'older_than_days':older_than_days}
