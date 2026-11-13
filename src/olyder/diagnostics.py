"""Read-only setup diagnostics; availability is not a live integration test."""
import platform
import shutil

from .adapters import agent_capabilities


def doctor():
    return {'schema_version':1,'python':platform.python_version(),
            'platform':platform.system(),'agents':agent_capabilities(),
            'executables':{n:shutil.which(n) is not None for n in ('codex','opencode','claude','docker','git')},
            'docker_daemon':'not_probed','provider_billing':'not_connected',
            'warnings':['Host execution is not OS isolation',
                        'CLI usage is post-hoc; billing may be unknown',
                        'Windows shell-script wrappers may require an explicit native argv adapter']}
