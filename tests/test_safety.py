import logging

from core.models import PluginResult
from core.processor import Processor


def test_subprocess_safety_input_validation(caplog):
    proc = Processor(scope=["example.com"])
    
    malicious_inputs = [
        "; rm -rf /",
        "$(whoami).example.com",
        "foo.example.com;whoami",
        "foo.example.com<script>alert(1)</script>",
        "foo.example.com`id`"
    ]
    
    with caplog.at_level(logging.WARNING):
        res = proc.process([
            PluginResult(
                plugin_name="EvilPlugin",
                subdomains=malicious_inputs + ["clean.example.com"]
            )
        ])
    
    assert "clean.example.com" in res.by_plugin["EvilPlugin"]
    for val in malicious_inputs:
        assert val not in res.by_plugin["EvilPlugin"]
        assert f"dropped invalid subdomain entry: {val.strip().lower()}" in caplog.text.lower()
