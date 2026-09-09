"""Local-only browser test fixture using the actual API and an isolated database."""
import argparse
from hashlib import sha256
from pathlib import Path
from time import time
from uuid import uuid4

from cryptography.fernet import Fernet
import uvicorn

from rpa_console.api import Config, create_app
from rpa_console.control import Control
from rpa_console.storage import Base, Database, LoginSession, ApplicationSource, PublishedApplication, ApplicationRelease, RobotDeployment, Robot


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', required=True)
    parser.add_argument('--port', type=int, default=4191)
    parser.add_argument('--web-port', type=int, default=4190)
    args = parser.parse_args()
    root = Path(args.directory).resolve()
    root.mkdir(mode=0o700)  # Refuse reuse of an existing directory or database.
    db = Database('sqlite:///' + str(root / 'fixture.db'))
    Base.metadata.create_all(db.engine)
    config = Config('unused', 'fixture-service-token', public_url=f'http://127.0.0.1:{args.web_port}',
                    evidence_dir=str(root / 'evidence'), admins=('fixture-admin',),
                    credential_encryption_key=Fernet.generate_key().decode())
    control = Control(db)
    robot = control.add_robot('离线验收机器人')
    schema = {'type': 'object', 'additionalProperties': False, 'required': ['brand_value'],
              'properties': {'brand_value': {'type': 'string', 'title': '品牌', 'minLength': 1}}}
    source_id, app_id = str(uuid4()), str(uuid4())
    inventory = []
    with db.transaction() as s:
        s.add(LoginSession(id=sha256(b'console-browser-fixture').hexdigest(), expires=time() + 3600,
                           data={'kind': 'user', 'name': '页面验收用户', 'open_id': 'fixture-admin'}))
        s.add(ApplicationSource(id=source_id, name='离线验收来源', url='https://example.invalid/repo'))
        s.flush()
        s.add(PublishedApplication(id=app_id, source_id=source_id, app_id='fixture.inventory', name='验收应用'))
        s.flush()
        for commit in ('a' * 40, 'b' * 40, 'c' * 40):
            release_id = str(uuid4())
            deployment = {'release_id': release_id, 'app_id': 'fixture.inventory', 'version': '1.0',
                          'commit': commit, 'schema_status': 'valid', 'input_schema': schema}
            s.add(ApplicationRelease(id=release_id, application_id=app_id, commit=commit, version='1.0',
                                    data={'app_id': 'fixture.inventory', 'input_schema': schema}))
            s.flush()
            if commit != 'c' * 40:
                s.add(RobotDeployment(robot_id=robot['id'], release_id=release_id, status='installed', data={}))
                inventory.append(deployment)
        s.get(Robot, robot['id']).capabilities = ['deploy-v1']
    control.reconcile(robot['id'], {'deployments': inventory})
    uvicorn.run(create_app(config, db), host='127.0.0.1', port=args.port)


if __name__ == '__main__':
    main()
