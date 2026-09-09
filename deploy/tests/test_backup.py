"""Explicit opt-in Docker recovery drill; all targets are disposable and isolated."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
from uuid import uuid4

import pytest

spec = importlib.util.spec_from_file_location('platform_backup', Path(__file__).parents[1] / 'backup.py')
backup_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup_module)


@pytest.mark.skipif(os.getenv('RPA_BACKUP_DOCKER_TEST') != '1', reason='isolated Docker recovery drill is opt-in')
def test_database_and_all_volumes_restore_with_original_key(tmp_path):
    from cryptography.fernet import Fernet
    from sqlalchemy import text, select
    from rpa_console.storage import Base, Database, Run
    from rpa_console.control import Control
    from rpa_console.credentials import CredentialStore
    from rpa_console.maintenance import set_mode, status

    run = backup_module.run
    prefix = 'rpa-recovery-test-' + uuid4().hex[:10]
    network, pg = prefix + '-net', prefix + '-pg'
    services = []
    try:
        run(['docker', 'network', 'create', network])
        run(['docker', 'run', '--rm', '-d', '--name', pg, '--network', network,
             '-e', 'POSTGRES_PASSWORD=verification-only', '-e', 'POSTGRES_DB=source', '-p', '127.0.0.1::5432', 'postgres:17'])
        # pg_isready is a bounded readiness probe, not a business operation.
        run(['docker', 'exec', pg, 'sh', '-c', 'for i in $(seq 1 30); do pg_isready -U postgres && exit 0; sleep 1; done; exit 1'])
        run(['docker', 'exec', pg, 'createdb', '-U', 'postgres', 'target'])
        port = run(['docker', 'port', pg, '5432']).split(':')[-1]
        source_db = Database(f'postgresql+psycopg://postgres:verification-only@127.0.0.1:{port}/source')
        target_db = Database(f'postgresql+psycopg://postgres:verification-only@127.0.0.1:{port}/target')
        Base.metadata.create_all(source_db.engine)
        with source_db.transaction() as s:
            s.execute(text('CREATE TABLE alembic_version (version_num varchar(32) PRIMARY KEY)'))
            s.execute(text("INSERT INTO alembic_version VALUES ('0005')"))
        key = Fernet.generate_key().decode()
        credentials = CredentialStore(key)
        control = Control(source_db, credentials=credentials)
        robot = control.add_robot('restore-fixture')
        control.reconcile(robot['id'], {'deployments': [{'app_id': 'fixture', 'version': '1'}]})
        secrets = {'username': 'restore-account', 'password': 'restore-password'}
        run_id = control.create_run(robot['id'], {'app_id': 'fixture', 'version': '1', 'inputs': {}}, 'restore-run', credentials=secrets)
        set_mode(source_db, True)
        env_file = tmp_path / 'deployment.env'
        env_file.write_text('# isolated test config\n')
        for database in ('source', 'target'):
            compose = tmp_path / (database + '.json')
            config = {'services': {name: {'image': 'postgres:17', 'command': ['sleep', 'infinity']} for name in backup_module.SERVICES},
                      'volumes': {name: {} for name in backup_module.VOLUMES},
                      'networks': {'database': {'external': True, 'name': network}}}
            config['services']['backend'].update(environment={
                'DATABASE_URL': f'postgresql+psycopg://postgres:verification-only@{pg}:5432/{database}',
                'CREDENTIAL_ENCRYPTION_KEY': key}, volumes=[name + ':/data/' + name for name in backup_module.VOLUMES], networks=['database'])
            compose.write_text(json.dumps(config))
            service = backup_module.Backup(compose, env_file, prefix + '-' + database)
            services.append(service)
            run([*service.compose, 'create'])
        source, target = services
        for name in backup_module.VOLUMES:
            source.volume(name, ['sh', '-c', 'printf "%s" "$1" > /volume/fixture', 'sh', 'fixture-' + name])
        destination = tmp_path / 'backup'
        source.create(destination)
        assert (destination / 'complete.json').is_file()
        assert destination.stat().st_mode & 0o777 == 0o700
        original_key = target.key
        target.key = 'wrong-key'
        with pytest.raises(ValueError, match='encryption key'):
            target.restore(destination)
        target.key = original_key
        target.volume('evidence', ['touch', '/volume/occupied-fixture'])
        with pytest.raises(ValueError, match='empty target volumes'):
            target.restore(destination)
        target.volume('evidence', ['rm', '/volume/occupied-fixture'])
        target.restore(destination)
        assert status(target_db)['maintenance'] is True
        with target_db.transaction() as s:
            assert s.get(Run, run_id).data['phase'] == 'queued'
            assert credentials.read(s, run_id) == secrets
            assert len(list(s.scalars(select(Run)))) == 1
        for name in backup_module.VOLUMES:
            assert target.volume(name, ['cat', '/volume/fixture'], readonly=True) == 'fixture-' + name
        with pytest.raises(ValueError, match='empty target database'):
            target.restore(destination)
        # Running service refusal happens before an output directory is created.
        run([*source.compose, 'start', 'web'])
        with pytest.raises(ValueError, match='stopped'):
            source.create(tmp_path / 'must-not-exist')
        assert not (tmp_path / 'must-not-exist').exists()
        source_db.engine.dispose()
        target_db.engine.dispose()
    finally:
        for service in services:
            subprocess.run([*service.compose, 'down', '--volumes'], capture_output=True)
        subprocess.run(['docker', 'stop', pg], capture_output=True)
        subprocess.run(['docker', 'network', 'rm', network], capture_output=True)
