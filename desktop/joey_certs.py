"""
JOEY - home security certificate for the phone app
Phones only allow a web page to use the microphone over a secure (https) connection.
This makes your own small "certificate authority" on your PC, and a certificate for your PC's
home address signed by it. You install the authority on your phone once, and then the phone trusts
Joey's https page - with no outside services. The private keys never leave your PC.

Needs:  pip install cryptography
"""

import datetime
import ipaddress
import socket
from pathlib import Path

FOLDER = Path(__file__).parent
CA_CERT = FOLDER / "joey_ca.crt"        # this one goes on the phone (safe to share with your own devices)
CA_KEY = FOLDER / "joey_ca.key"         # private: never share
SERVER_CERT = FOLDER / "joey_server.crt"
SERVER_KEY = FOLDER / "joey_server.key"


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def ensure_ca():
    """Make the home certificate authority once (valid 10 years)."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    if CA_CERT.exists() and CA_KEY.exists():
        return
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Joey Home Certificate"),
                      x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Joey & Ryan (this PC only)")])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(_now() - datetime.timedelta(days=1))
            .not_valid_after(_now() + datetime.timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True,
                                         content_commitment=False, key_encipherment=False,
                                         data_encipherment=False, key_agreement=False,
                                         encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .sign(key, hashes.SHA256()))
    CA_KEY.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                         serialization.NoEncryption()))
    CA_CERT.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def server_cert_for(ip: str):
    """A certificate for this PC's home address (remade if the address changes). Returns (cert, key) paths."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    ensure_ca()
    if SERVER_CERT.exists() and SERVER_KEY.exists():
        try:
            existing = x509.load_pem_x509_certificate(SERVER_CERT.read_bytes())
            ips = existing.extensions.get_extension_for_class(x509.SubjectAlternativeName).value \
                .get_values_for_type(x509.IPAddress)
            if ipaddress.ip_address(ip) in ips and existing.not_valid_after_utc > _now() + datetime.timedelta(days=30):
                return SERVER_CERT, SERVER_KEY
        except Exception:
            pass
    ca_key = serialization.load_pem_private_key(CA_KEY.read_bytes(), password=None)
    ca_cert = x509.load_pem_x509_certificate(CA_CERT.read_bytes())
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    host = socket.gethostname()
    names = [x509.IPAddress(ipaddress.ip_address(ip)), x509.DNSName(host), x509.DNSName(f"{host}.local"),
             x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
    cert = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"Joey on {host}")]))
            .issuer_name(ca_cert.subject).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(_now() - datetime.timedelta(days=1))
            .not_valid_after(_now() + datetime.timedelta(days=800))   # phones accept up to 825 days
            .add_extension(x509.SubjectAlternativeName(names), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            .sign(ca_key, hashes.SHA256()))
    SERVER_KEY.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                             serialization.NoEncryption()))
    SERVER_CERT.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return SERVER_CERT, SERVER_KEY
