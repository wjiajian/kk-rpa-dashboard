"""Opt-in startup and restart verification using separately tagged current images."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.error import URLError
from urllib.request import urlopen
from uuid import uuid4

from cryptography.fernet import Fernet
import pytest

spec = importlib.util.spec_from_file_location('compose_test_tools', Path(__file__).parents[1] / 'backup.py')
tools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tools)


@pytest.mark.skipif(os.getenv('RPA_COMPOSE_DOCKER_TEST') != '1', reason='current-image Compose verification is opt-in')
def test_current_four_services_migrate_and_retain_queue_in_maintenance(tmp_path):
    run = tools.run
    project = 'rpa-compose-test-' + uuid4().hex[:10]
    network, postgres = project + '-db', project + '-postgres'
    compose = None
    try:
        run(['docker', 'network', 'create', network])
        run(['docker', 'run', '--rm', '-d', '--name', postgres, '--network', network,
             '-e', 'POSTGRES_PASSWORD=fixture', '-e', 'POSTGRES_DB=console', 'postgres:17'])
        run(['docker', 'exec', postgres, 'sh', '-c', 'for i in $(seq 1 30); do pg_isready -U postgres && exit 0; sleep 1; done; exit 1'])
        env = {'DATABASE_URL': f'postgresql+psycopg://postgres:fixture@{postgres}:5432/console',
               'POSTGRES_NETWORK': network, 'CREDENTIAL_ENCRYPTION_KEY': Fernet.generate_key().decode(),
               'PUBLIC_URL': 'https://console.example.invalid', 'WEB_PORT': '0',
               'AGENT_INTERNAL_TOKEN': 'fixture-internal', 'DEEPSEEK_API_KEY': 'fixture-unused',
               'FEISHU_APP_ID': 'fixture', 'FEISHU_APP_SECRET': 'fixture', 'FEISHU_TENANT_KEY': 'fixture',
               'ADMIN_OPEN_IDS': 'fixture-admin'}
        env_file = tmp_path / '.env'
        env_file.write_text('\n'.join(f"{key}='{value}'" for key, value in env.items()))
        os.chmod(env_file, 0o600)
        original = Path(__file__).parents[1] / 'compose.yaml'
        config = json.loads(run(['docker', 'compose', '--env-file', str(env_file), '-f', str(original), '-p', project, 'config', '--format', 'json']))
        for name, service in config['services'].items():
            service.pop('build', None)
            image = 'backend' if name == 'publisher' else name
            service['image'] = f'rpa-platform-verification-{image}:local'
            run(['docker', 'image', 'inspect', service['image']])
        config_file = tmp_path / 'compose.json'
        config_file.write_text(json.dumps(config))
        compose = ['docker', 'compose', '-f', str(config_file), '-p', project]
        run([*compose, 'up', '-d', '--no-build'])
        base = 'http://' + run([*compose, 'port', 'web', '80'])
        ready = False
        for _ in range(60):
            try:
                with urlopen(base + '/api/health', timeout=2) as response:
                    ready = json.load(response) == {'status': 'ok', 'mode': 'live'}
                if ready:
                    break
            except (OSError, URLError):
                pass
            time.sleep(0.5)
        assert ready, 'Current backend did not become ready through the Web proxy'
        with urlopen(base + '/tasks/new', timeout=2) as response:
            assert b'id="root"' in response.read()
        agent = run([*compose, 'exec', '-T', 'agent', 'node', '-e', "fetch('http://127.0.0.1:3001/health').then(async r=>{if(!r.ok)process.exit(1);console.log(await r.text())})"])
        assert json.loads(agent) == {'active': 0}
        run([*compose, 'exec', '-T', 'publisher', 'git', '--version'])
        for _ in range(20):
            logs = run([*compose, 'logs', '--no-color', 'backend'])
            if '/internal/agent/work' in logs:
                break
            time.sleep(0.25)
        assert '/internal/agent/work HTTP/1.1" 200 OK' in logs
        publisher_probe = """import os,time
from rpa_console.storage import Database,ImportJob
from rpa_console.credentials import CredentialStore
from rpa_console.publishing import Publishing
db=Database(os.environ['DATABASE_URL'])
p=Publishing(db,CredentialStore(os.environ['CREDENTIAL_ENCRYPTION_KEY']),'/data/artifacts')
source=p.add_source('container-loopback-fixture','https://127.0.0.1:9/unavailable.git')
job=p.import_source(source['id'],'main')
for attempt in range(40):
 with db.transaction() as s:
  state=s.get(ImportJob,job['id']).status
 if state=='failed':
  print('publisher processed unavailable source')
  break
 time.sleep(0.25)
else:
 raise RuntimeError('publisher did not process the queued import')
"""
        assert run([*compose, 'exec', '-T', 'backend', 'uv', 'run', '--no-sync', 'python', '-c', publisher_probe]) == 'publisher processed unavailable source'
        seed = """import os
from rpa_console.storage import Database
from rpa_console.control import Control
from rpa_console.credentials import CredentialStore
c=Control(Database(os.environ['DATABASE_URL']),credentials=CredentialStore(os.environ['CREDENTIAL_ENCRYPTION_KEY']))
r=c.add_robot('container-restart-fixture')
c.reconcile(r['id'],{'deployments':[{'app_id':'fixture','version':'1'}]})
print(c.create_run(r['id'],{'app_id':'fixture','version':'1','inputs':{}},'queued-fixture',credentials={'username':'fixture','password':'fixture'}))
"""
        run_id = run([*compose, 'exec', '-T', 'backend', 'uv', 'run', '--no-sync', 'python', '-c', seed])
        state = json.loads(run([*compose, 'exec', '-T', 'backend', 'uv', 'run', '--no-sync', 'python', '-m', 'rpa_console.maintenance', 'enter']))
        assert state['maintenance'] and state['drained']
        run([*compose, 'restart', 'backend'])
        # This read runs against the same database after the container restart.
        verify = """import os,json
from sqlalchemy import text
from rpa_console.storage import Database,Run
from rpa_console.maintenance import status
db=Database(os.environ['DATABASE_URL'])
assert status(db)['maintenance']
with db.transaction() as s:
 assert s.get(Run,os.environ['VERIFY_RUN_ID']).data['phase']=='queued'
 assert s.scalar(text('SELECT version_num FROM alembic_version'))=='0005'
print('queue and maintenance persisted')
"""
        output = run([*compose, 'exec', '-T', '-e', 'VERIFY_RUN_ID=' + run_id, 'backend', 'uv', 'run', '--no-sync', 'python', '-c', verify])
        assert output == 'queue and maintenance persisted'
        containers = json.loads(run(['docker', 'inspect', *run([*compose, 'ps', '-q']).splitlines()]))
        assert len(containers) == 4
        assert all(row['State']['Running'] for row in containers)
    finally:
        if compose:
            subprocess.run([*compose, 'down', '--volumes'], capture_output=True)
        subprocess.run(['docker', 'stop', postgres], capture_output=True)
        subprocess.run(['docker', 'network', 'rm', network], capture_output=True)
