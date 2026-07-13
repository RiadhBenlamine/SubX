import pytest

from core.models import PluginResult
from core.processor import (Processor, matches_boundary,
                            normalize_and_validate_domain)


def test_normalize_and_validate():
    assert normalize_and_validate_domain("EXAMPLE.COM.") == "example.com"
    assert normalize_and_validate_domain("  example.com  ") == "example.com"
    
    with pytest.raises(ValueError):
        normalize_and_validate_domain("")
    with pytest.raises(ValueError):
        normalize_and_validate_domain("a..b.com")
    with pytest.raises(ValueError):
        normalize_and_validate_domain("-a.com")
    with pytest.raises(ValueError):
        normalize_and_validate_domain("a.com-")
    with pytest.raises(ValueError):
        normalize_and_validate_domain("example.com/test")

def test_boundary_matching():
    assert matches_boundary("a.example.com", "example.com") is True
    assert matches_boundary("example.com", "example.com") is True
    assert matches_boundary("notexample.com", "example.com") is False
    assert matches_boundary("a.b.example.com", "example.com") is True

def test_processor_scope():
    proc = Processor(scope=["example.com"], out_of_scope=["testing.example.com"])
    
    res = proc.process([
        PluginResult(
            plugin_name="Dummy",
            subdomains=["testing.example.com", "nottesting.example.com", "example.com"]
        )
    ])
    
    assert "nottesting.example.com" in res.by_plugin["Dummy"]
    assert "example.com" in res.by_plugin["Dummy"]
    assert "testing.example.com" not in res.by_plugin["Dummy"]
    assert "testing.example.com" in res.out_of_scope
