from geppetto_automation.secrets import SecretResolver


def test_secret_resolver_plaintext_with_key(monkeypatch):
    resolver = SecretResolver()

    class FakeClient:
        def get_secret_value(self, SecretId):
            assert SecretId == "plain"
            return {"SecretString": "mypassword"}

    class FakeBoto3:
        def client(self, name):
            assert name == "secretsmanager"
            return FakeClient()

    monkeypatch.setattr("geppetto_automation.secrets.boto3", FakeBoto3())

    values = resolver.resolve({"password": {"aws_secret": "plain", "key": "password"}})
    assert values["password"] == "mypassword"
