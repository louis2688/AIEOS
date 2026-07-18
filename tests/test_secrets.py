import pytest

from aeios.secrets import is_sealed, seal, unseal


def test_seal_roundtrip() -> None:
    token = seal("sk-hello-world", "master-key")
    assert is_sealed(token)
    assert unseal(token, "master-key") == "sk-hello-world"


def test_wrong_key_fails() -> None:
    token = seal("secret", "correct")
    with pytest.raises(ValueError, match="MAC"):
        unseal(token, "wrong")
