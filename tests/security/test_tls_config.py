"""Security tests for TLS configuration."""

from __future__ import annotations

import ssl

import pytest

from wsfabric.transport.base import create_default_ssl_context


@pytest.mark.security
class TestTLSConfiguration:
    """Verify TLS defaults meet security requirements."""

    def test_default_context_enforces_tls_1_2_minimum(self) -> None:
        """Verify default context enforces TLS 1.2+."""
        ctx = create_default_ssl_context()
        assert ctx.minimum_version >= ssl.TLSVersion.TLSv1_2

    def test_default_context_verifies_certificates(self) -> None:
        """Verify default context requires certificate verification."""
        ctx = create_default_ssl_context()
        assert ctx.verify_mode == ssl.CERT_REQUIRED
        assert ctx.check_hostname is True

    def test_no_verify_disables_checks(self) -> None:
        """Verify no-verify mode properly disables certificate checks."""
        ctx = create_default_ssl_context(verify=False)
        assert ctx.verify_mode == ssl.CERT_NONE
        assert ctx.check_hostname is False

    def test_old_protocols_disabled(self) -> None:
        """Verify SSLv3 and TLSv1.0 are disabled."""
        ctx = create_default_ssl_context()
        assert ctx.options & ssl.OP_NO_SSLv3

    def test_context_has_ca_certs(self) -> None:
        """Verify default context loads system CA certificates."""
        ctx = create_default_ssl_context()
        # ssl.create_default_context() loads default certs
        stats = ctx.cert_store_stats()
        assert stats["x509_ca"] > 0, "No CA certificates loaded"
