import ipaddress
import socket
from urllib.parse import urlparse

# Blocked IPv4 networks (RFC 1918, RFC 3927, Loopback, Cloud Metadata, Multicast, Reserved)
BLOCKED_IPV4_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),  # Current network
    ipaddress.ip_network("10.0.0.0/8"),  # Private class A
    ipaddress.ip_network("100.64.0.0/10"),  # Shared address space / CGNAT
    ipaddress.ip_network("127.0.0.0/8"),  # Loopback
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local & Cloud Metadata (169.254.169.254)
    ipaddress.ip_network("172.16.0.0/12"),  # Private class B
    ipaddress.ip_network("192.0.0.0/24"),  # IETF Protocol Assignments
    ipaddress.ip_network("192.0.2.0/24"),  # TEST-NET-1
    ipaddress.ip_network("192.88.99.0/24"),  # 6to4 relay
    ipaddress.ip_network("192.168.0.0/16"),  # Private class C
    ipaddress.ip_network("198.18.0.0/15"),  # Network benchmark tests
    ipaddress.ip_network("198.51.100.0/24"),  # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),  # TEST-NET-3
    ipaddress.ip_network("224.0.0.0/4"),  # Multicast
    ipaddress.ip_network("240.0.0.0/4"),  # Reserved / Future use
    ipaddress.ip_network("255.255.255.255/32"),  # Broadcast
]

# Blocked IPv6 networks
BLOCKED_IPV6_NETWORKS = [
    ipaddress.ip_network("::1/128"),  # Loopback
    ipaddress.ip_network("::/128"),  # Unspecified
    ipaddress.ip_network("fc00::/7"),  # Unique local (ULA)
    ipaddress.ip_network("fe80::/10"),  # Link-local unicast
    ipaddress.ip_network("ff00::/8"),  # Multicast
]

FORBIDDEN_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "instance-data",
}


class SSRFSecurityException(ValueError):
    """Raised when a URL targets a prohibited or internal network resource."""

    pass


def is_ip_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True if the given IP address falls within any blocked subnet."""
    if isinstance(ip, ipaddress.IPv4Address):
        return any(ip in network for network in BLOCKED_IPV4_NETWORKS)

    if isinstance(ip, ipaddress.IPv6Address):
        # Handle IPv4-mapped IPv6 addresses (e.g. ::ffff:127.0.0.1)
        if ip.ipv4_mapped:
            return is_ip_blocked(ip.ipv4_mapped)
        return any(ip in network for network in BLOCKED_IPV6_NETWORKS)

    return True


def validate_target_url(url: str, allow_private: bool = False) -> str:
    """
    Validate that a given target URL is safe to crawl and cannot be used
    for Server-Side Request Forgery (SSRF) attacks.

    Parameters:
        url: The candidate URL string to audit.
        allow_private: If True, bypasses private IP validation (for local testing only).

    Returns:
        The sanitized and normalized URL string.

    Raises:
        SSRFSecurityException: If the URL scheme or resolved target IP is prohibited.
    """
    if not url or not isinstance(url, str):
        raise SSRFSecurityException("URL cannot be empty.")

    url = url.strip()
    parsed = urlparse(url)

    # 1. Enforce strict HTTP/HTTPS protocol
    if parsed.scheme.lower() not in ("http", "https"):
        raise SSRFSecurityException(
            f"Prohibited URL scheme '{parsed.scheme}'. Only 'http' and 'https' are permitted."
        )

    hostname = parsed.hostname
    if not hostname:
        raise SSRFSecurityException("URL is missing a valid hostname.")

    hostname_lower = hostname.lower()

    # 2. Check forbidden hostnames
    if hostname_lower in FORBIDDEN_HOSTNAMES or hostname_lower.endswith(".localhost"):
        if not allow_private:
            raise SSRFSecurityException(f"Prohibited hostname: '{hostname}'.")

    # 3. Check if hostname is directly an IP literal
    try:
        ip = ipaddress.ip_address(hostname_lower)
        if not allow_private and is_ip_blocked(ip):
            raise SSRFSecurityException(
                f"Prohibited target IP address: '{ip}'. Private/internal destinations are blocked."
            )
        return url
    except ValueError:
        # Hostname is a domain name, proceed to DNS resolution
        pass

    # 4. Resolve DNS and check all resolved IP addresses
    if not allow_private:
        try:
            port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
            addr_info = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)

            resolved_ips = {item[4][0] for item in addr_info}
            if not resolved_ips:
                raise SSRFSecurityException(f"Could not resolve hostname: '{hostname}'.")

            for resolved_ip_str in resolved_ips:
                ip = ipaddress.ip_address(resolved_ip_str)
                if is_ip_blocked(ip):
                    raise SSRFSecurityException(
                        f"Prohibited resolved IP '{resolved_ip_str}' for hostname '{hostname}'. "
                        "Access to internal network ranges is blocked."
                    )
        except socket.gaierror as e:
            raise SSRFSecurityException(f"DNS resolution failure for '{hostname}': {e}") from e

    return url
