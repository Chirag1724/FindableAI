import pytest

from app.core.security import SSRFSecurityException, validate_target_url


def test_valid_public_urls():
    """Verify that public HTTP/HTTPS URLs pass validation."""
    valid_urls = [
        "https://example.com",
        "https://example.com/pricing",
        "http://example.com:8080/path?query=1",
    ]
    for url in valid_urls:
        assert validate_target_url(url) == url


def test_prohibited_schemes():
    """Verify that non-http/https schemes are rejected."""
    prohibited = [
        "file:///etc/passwd",
        "ftp://ftp.example.com",
        "gopher://example.com",
        "javascript:alert(1)",
        "data:text/html,hello",
        "ssh://user@example.com",
    ]
    for url in prohibited:
        with pytest.raises(SSRFSecurityException, match="Prohibited URL scheme"):
            validate_target_url(url)


def test_loopback_ips_blocked():
    """Verify loopback addresses are blocked."""
    loopbacks = [
        "http://127.0.0.1",
        "http://127.0.0.1:8000/api",
        "http://127.0.1.1",
        "http://[::1]/status",
    ]
    for url in loopbacks:
        with pytest.raises(SSRFSecurityException):
            validate_target_url(url)


def test_cloud_metadata_blocked():
    """Verify AWS/GCP/Azure link-local metadata endpoints (169.254.169.254) are blocked."""
    metadata_urls = [
        "http://169.254.169.254",
        "http://169.254.169.254/latest/meta-data/",
        "http://169.254.1.1",
    ]
    for url in metadata_urls:
        with pytest.raises(SSRFSecurityException):
            validate_target_url(url)


def test_private_subnets_blocked():
    """Verify RFC 1918 private subnets are blocked."""
    privates = [
        "http://10.0.0.1",
        "http://10.254.254.254:8080",
        "http://172.16.0.1",
        "http://172.31.255.255",
        "http://192.168.0.1",
        "http://192.168.1.100:3000",
    ]
    for url in privates:
        with pytest.raises(SSRFSecurityException):
            validate_target_url(url)


def test_localhost_hostname_blocked():
    """Verify localhost hostnames are rejected."""
    local_hosts = [
        "http://localhost",
        "http://localhost:3000",
        "http://api.localhost",
    ]
    for url in local_hosts:
        with pytest.raises(SSRFSecurityException):
            validate_target_url(url)


def test_allow_private_mode():
    """Verify that allow_private=True bypasses the check for local tests."""
    assert (
        validate_target_url("http://127.0.0.1:8080", allow_private=True) == "http://127.0.0.1:8080"
    )
    assert (
        validate_target_url("http://localhost:3000", allow_private=True) == "http://localhost:3000"
    )


def test_empty_or_malformed_urls():
    """Verify empty or None URLs raise SSRFSecurityException."""
    with pytest.raises(SSRFSecurityException, match="URL cannot be empty"):
        validate_target_url("")

    with pytest.raises(SSRFSecurityException, match="URL cannot be empty"):
        validate_target_url(None)  # type: ignore

    with pytest.raises(SSRFSecurityException, match="missing a valid hostname"):
        validate_target_url("http://")
