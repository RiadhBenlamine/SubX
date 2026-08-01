from core.ui.banner import _is_newer_version, banner, get_version


def test_version_retrieval():
    ver = get_version()
    assert isinstance(ver, str)
    assert len(ver) > 0


def test_is_newer_version():
    assert _is_newer_version("2.0.4", "2.0.5") is True
    assert _is_newer_version("2.0.4", "2.1.0") is True
    assert _is_newer_version("2.0.4", "3.0.0") is True
    assert _is_newer_version("2.0.4", "2.0.4") is False
    assert _is_newer_version("2.0.4", "2.0.3") is False


def test_banner_rendering():
    # Verify banner function executes without throwing exceptions
    banner("2.0.4")
