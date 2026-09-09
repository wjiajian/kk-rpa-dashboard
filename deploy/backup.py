#!/usr/bin/env python3
"""Offline Compose backup and restore to an empty database and empty volumes."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
from urllib.parse import unquote, urlsplit

SERVICES = ('web', 'backend', 'agent', 'publisher')
VOLUMES = ('evidence', 'sessions', 'artifacts', 'git_config')


def run(args, *, env=None, output=None):
    result = subprocess.run(args, stdout=output if output else subprocess.PIPE, stderr=subprocess.PIPE, text=output is None, env=env)
    if result.returncode:
        # Docker configuration and database errors can contain credentials.
        raise RuntimeError(f'{args[0]} operation failed (exit {result.returncode}); check configuration and service logs')
    return result.stdout.strip() if output is None else ""


class Backup:
    def __init__(self, compose, env_file, project=None, image='postgres:17'):
        self.env_file = Path(env_file).resolve()
        self.compose = ['docker', 'compose', '--env-file', str(self.env_file), '-f', str(Path(compose).resolve())]
        if project:
            self.compose += ['--project-name', project]
        self.config = json.loads(run([*self.compose, 'config', '--format', 'json']))
        self.image = image
        environment = self.config['services']['backend']['environment']
        self.key = environment['CREDENTIAL_ENCRYPTION_KEY']
        url = urlsplit(environment['DATABASE_URL'].replace('postgresql+psycopg:', 'postgresql:', 1))
        if url.scheme != 'postgresql' or not url.hostname or not url.username or url.query or url.fragment:
            raise ValueError('Use a PostgreSQL URL without query parameters for this backup tool')
        self.pg_env = {**os.environ, 'PGPASSWORD': unquote(url.password or '')}
        self.pg_args = ['-h', url.hostname, '-p', str(url.port or 5432), '-U', unquote(url.username), '-d', unquote(url.path.lstrip('/'))]
        self.network = self.config['networks']['database']['name']
        self.volumes = {name: self.config['volumes'][name]['name'] for name in VOLUMES}

    def stopped(self):
        for service in SERVICES:
            ids = run([*self.compose, 'ps', '--all', '--quiet', service]).splitlines()
            if not ids:
                raise ValueError('Create the Compose containers without starting them before backup/restore')
            for container in json.loads(run(['docker', 'inspect', *ids])):
                if container['State']['Status'] not in {'created', 'exited'}:
                    raise ValueError('All four application services must be stopped')
        for volume in self.volumes.values():
            run(['docker', 'volume', 'inspect', volume])
            if run(['docker', 'ps', '--quiet', '--filter', 'volume=' + volume]):
                raise ValueError('A persistent volume is still mounted by a running container')

    def database(self, command, args, directory=None, readonly=False, output=None):
        docker = ['docker', 'run', '--rm', '--network', self.network, '--env', 'PGPASSWORD']
        if directory:
            docker += ['-v', str(directory) + ':/backup' + (':ro' if readonly else '')]
        return run([*docker, self.image, command, *self.pg_args, *args], env=self.pg_env, output=output)

    def sql(self, sql):
        return self.database('psql', ['-X', '-v', 'ON_ERROR_STOP=1', '-Atc', sql])

    def volume(self, name, args, directory=None, readonly=False, output=None):
        docker = ['docker', 'run', '--rm', '--network', 'none', '-v', self.volumes[name] + ':/volume' + (':ro' if readonly else '')]
        if directory:
            docker += ['-v', str(directory) + ':/backup' + ('' if readonly else ':ro')]
        return run([*docker, self.image, *args], output=output)

    def create(self, destination):
        self.stopped()
        drained = self.sql("SELECT maintenance AND NOT EXISTS (SELECT 1 FROM robots WHERE active_run IS NOT NULL OR deployment_job IS NOT NULL) AND NOT EXISTS (SELECT 1 FROM import_jobs WHERE status='fetching') FROM service_state WHERE id=1")
        if drained != 't':
            raise ValueError('Enter maintenance and drain all active jobs before backup')
        destination = Path(destination).resolve()
        destination.mkdir(mode=0o700)  # Never overwrite another backup, including an incomplete one.
        shutil.copyfile(self.env_file, destination / 'deployment.env')
        (destination / 'compose.json').write_text(json.dumps(self.config, indent=2))
        os.chmod(destination / 'deployment.env', 0o600)
        os.chmod(destination / 'compose.json', 0o600)
        with (destination / 'database.dump').open('wb') as output:
            self.database('pg_dump', ['--format=custom'], output=output)
        for name in VOLUMES:
            with (destination / (name + '.tar')).open('wb') as output:
                self.volume(name, ['tar', '-cf', '-', '-C', '/volume', '.'], readonly=True, output=output)
        self.stopped()
        metadata = {'format': 1, 'created': datetime.now(timezone.utc).isoformat(), 'volumes': list(VOLUMES),
                    'postgres_client_image': self.image, 'migration': self.sql('SELECT version_num FROM alembic_version')}
        (destination / 'complete.json').write_text(json.dumps(metadata, indent=2))
        for path in destination.iterdir():
            path.chmod(0o600)

    def restore(self, source):
        self.stopped()
        source = Path(source).resolve()
        metadata = json.loads((source / 'complete.json').read_text())
        if metadata.get('format') != 1 or metadata.get('volumes') != list(VOLUMES):
            raise ValueError('Unsupported or incomplete backup')
        original = json.loads((source / 'compose.json').read_text())
        if original['services']['backend']['environment']['CREDENTIAL_ENCRYPTION_KEY'] != self.key:
            raise ValueError('Target must use the original credential encryption key')
        for name in ['database.dump', 'deployment.env', *(name + '.tar' for name in VOLUMES)]:
            if not (source / name).is_file():
                raise ValueError('Backup is missing a required file')
        objects = self.sql("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON c.relnamespace=n.oid WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%' AND c.relkind IN ('r','p','v','m','S','f')")
        if objects != '0':
            raise ValueError('Restore requires an empty target database; existing data will not be overwritten')
        for name in VOLUMES:
            if self.volume(name, ['find', '/volume', '-mindepth', '1', '-print', '-quit'], readonly=True):
                raise ValueError('Restore requires empty target volumes')
            # Check all volume archives before mutating any target.
            self.volume(name, ['tar', '-tf', '/backup/' + name + '.tar'], source)
        self.database('pg_restore', ['--exit-on-error', '--single-transaction', '--no-owner', '--no-privileges', '/backup/database.dump'], source, readonly=True)
        for name in VOLUMES:
            self.volume(name, ['tar', '--keep-old-files', '-xf', '/backup/' + name + '.tar', '-C', '/volume'], source)
        if self.sql('SELECT maintenance FROM service_state WHERE id=1') != 't':
            raise ValueError('Restored database is not in maintenance; keep services stopped')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['create', 'restore'])
    parser.add_argument('directory')
    parser.add_argument('--compose', default=str(Path(__file__).with_name('compose.yaml')))
    parser.add_argument('--env-file', default=str(Path(__file__).with_name('.env')))
    parser.add_argument('--project')
    parser.add_argument('--postgres-image', default='postgres:17')
    args = parser.parse_args()
    try:
        backup = Backup(args.compose, args.env_file, args.project, args.postgres_image)
        getattr(backup, args.action)(args.directory)
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        # Exception types from filesystem/config parsing may contain private paths; no raw config output.
        print(str(error) if isinstance(error, (ValueError, RuntimeError)) and not isinstance(error, json.JSONDecodeError)
              else 'Backup/restore failed: ' + type(error).__name__)
        raise SystemExit(1)
    print('Backup complete.' if args.action == 'create' else 'Restore complete. Keep maintenance enabled until verification passes.')


if __name__ == '__main__':
    main()
