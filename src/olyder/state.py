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
        if self.root.is_symlink():
            raise StateError('Run storage cannot be a symlink')
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.db = self.root/'runs.sqlite3'
        if self.db.is_symlink():
            raise StateError('Run database cannot be a symlink')
        with self.connect() as c:
            c.execute('CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, revision INTEGER, data TEXT)')

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
        if path.is_symlink():
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
