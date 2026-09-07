"""Run credentials are encrypted separately from snapshots, operations and events."""
import json

from cryptography.fernet import Fernet, InvalidToken

from .storage import RunCredential


class CredentialError(ValueError):
    pass


class CredentialStore:
    def __init__(self, key):
        self.cipher = Fernet(key)

    def save(self, session, run_id, credentials):
        payload = json.dumps({"run_id": run_id, "credentials": credentials}).encode()
        session.add(RunCredential(run_id=run_id, encrypted=self.cipher.encrypt(payload).decode()))

    def read(self, session, run_id):
        row = session.get(RunCredential, run_id)
        if row is None:
            raise CredentialError("原运行没有保存业务凭据，请在控制台重新发起运行并填写账号密码")
        try:
            payload = json.loads(self.cipher.decrypt(row.encrypted))
        except (InvalidToken, ValueError):
            raise CredentialError("业务凭据无法解密，请检查服务端原有 CREDENTIAL_ENCRYPTION_KEY") from None
        if payload.get("run_id") != run_id:
            raise CredentialError("业务凭据与运行不匹配")
        return payload["credentials"]
