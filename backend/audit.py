"""Append-preserving JSON audit log with file lock and atomic replacement."""
from datetime import datetime, timezone
import json
import os
import time
from pathlib import Path
from uuid import uuid4

from filelock import FileLock
from pydantic_core import to_jsonable_python


def public_evidence(value):
    """Keep observable results, never provider reasoning or credential fields."""
    if isinstance(value, dict):
        if value.get('part_kind') == 'thinking':
            return {'part_kind': 'thinking', 'content_omitted': True}
        return {key: ('[redacted]' if key.lower() in {'api_key', 'human_capability', 'authorization'}
                      else public_evidence(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [public_evidence(item) for item in value]
    return value


class AuditTrail:
    def __init__(self, path: Path):
        self.path = path

    def append(self, *, ticket: int | None, agent: str, event: str, run_id: str,
               delegation=None, tool_calls=None, results=None, approval_requests=None):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            'timestamp_utc': datetime.now(timezone.utc).isoformat(),
            'run_id': run_id, 'ticket': ticket, 'agent': agent, 'event': event,
            'delegation': delegation, 'tool_calls': tool_calls or [],
            'results': results, 'approval_requests': approval_requests or [],
        }
        # Never include secrets/credentials in these arguments. No truncation of
        # operational tool results; corruption is an error, never overwritten.
        entry = public_evidence(to_jsonable_python(entry))
        with FileLock(str(self.path) + '.lock', timeout=10):
            data = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else []
            if isinstance(data, list):
                entries = data
            elif isinstance(data, dict) and isinstance(data.get('entries'), list):
                entries = data['entries']
            else:
                raise ValueError('Audit log must be an array or an object with an entries array')
            entry['sequence'] = len(entries) + 1
            entries.append(entry)
            temporary = self.path.with_name(self.path.name + '.' + uuid4().hex + '.tmp')
            try:
                with temporary.open('w', encoding='utf-8') as file:
                    json.dump(data, file, ensure_ascii=False, indent=2)
                    file.write('\n')
                    file.flush()
                    os.fsync(file.fileno())
                # Windows scanners/sync clients can briefly hold the destination.
                # Retry the same atomic replacement under the existing lock;
                # never fall back to truncating the preserved audit file.
                for attempt in range(8):
                    try:
                        os.replace(temporary, self.path)
                        break
                    except PermissionError:
                        if attempt == 7:
                            raise
                        time.sleep(min(.05 * 2 ** attempt, .5))
            finally:
                if temporary.exists():
                    temporary.unlink()
