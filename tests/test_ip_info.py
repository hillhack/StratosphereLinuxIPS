"""Unit test for modules/ip_info/ip_info.py"""

from tests.module_factory import ModuleFactory
import maxminddb
import pytest
from unittest.mock import Mock, patch
import json
import requests
import socket
import subprocess
from slips_files.core.evidence_structure.evidence import (
    ThreatLevel,
    Evidence,
    Proto,
    EvidenceType,
    IoCType,
    Direction,
    IDEACategory,
    Tag,
)


@pytest.mark.parametrize(
    "ip_address, expected_geocountry",
    [  # Testcase 1: Valid IP address
        ("153.107.41.230", {"geocountry": "Australia"}),
        # Testcase 2: Private IP address
        ("192.168.1.1", {"geocountry": "Private"}),
        # Testcase 3: Private IPv6 address
        ("2001:db8::1", {"geocountry": "Private"}),
        # Testcase 4: IP address not found in database
        ("23.188.195.255", {"geocountry": "Unknown"}),
    ],
)
def test_get_geocountry(mock_db, ip_address, expected_geocountry):
    ip_info = ModuleFactory().create_ip_info_obj(mock_db)
    ip_info.country_db = maxminddb.open_database(
        "databases/GeoLite2-Country.mmdb"
    )
    assert ip_info.get_geocountry(ip_address) == expected_geocountry


def test_get_vendor_from_database(mocker, mock_db):
    ip_info = ModuleFactory().create_ip_info_obj(mock_db)
    mac_addr = "08:00:27:7f:09:e1"
    profileid = "profile_10.0.2.15"
    db_vendor = "Database Vendor"

    mock_db.get_mac_vendor_from_profile.return_value = db_vendor

    result = ip_info.get_vendor(mac_addr, profileid)
    expected_result = True
    assert result == expected_result
    (mock_db.get_mac_vendor_from_profile.assert_called_once_with(profileid))
    mocker.patch.object(ip_info, "get_vendor_offline").assert_not_called()
    mocker.patch.object(ip_info, "get_vendor_online").assert_not_called()


def test_get_vendor_from_offline(mocker, mock_db):
    ip_info = ModuleFactory().create_ip_info_obj(mock_db)
    mac_addr = "08:00:27:7f:09:e2"
    profileid = "profile_10.0.2.16"
    offline_vendor = "Offline Vendor"

    mock_db.get_mac_vendor_from_profile.return_value = None
    mocker.patch.object(
        ip_info, "get_vendor_offline", return_value=offline_vendor
    )

    result = ip_info.get_vendor(mac_addr, profileid)

    assert result == {"MAC": mac_addr, "Vendor": offline_vendor}
    (mock_db.get_mac_vendor_from_profile.assert_called_once_with(profileid))
    (ip_info.get_vendor_offline.assert_called_once_with(mac_addr, profileid))
    mocker.patch.object(ip_info, "get_vendor_online").assert_not_called()
    mock_db.set_mac_vendor_to_profile.assert_called_once_with(
        profileid, mac_addr, offline_vendor
    )


def test_get_vendor_from_online(mocker, mock_db):
    ip_info = ModuleFactory().create_ip_info_obj(mock_db)
    mac_addr = "08:00:27:7f:09:e3"
    profileid = "profile_10.0.2.17"
    online_vendor = "Online Vendor"

    mock_db.get_mac_vendor_from_profile.return_value = None
    mocker.patch.object(ip_info, "get_vendor_offline", return_value=None)
    mocker.patch.object(
        ip_info, "get_vendor_online", return_value=online_vendor
    )

    result = ip_info.get_vendor(mac_addr, profileid)

    assert result == {"MAC": mac_addr, "Vendor": online_vendor}
    (mock_db.get_mac_vendor_from_profile.assert_called_once_with(profileid))
    (ip_info.get_vendor_offline.assert_called_once_with(mac_addr, profileid))
    (ip_info.get_vendor_online.assert_called_once_with(mac_addr))
    mock_db.set_mac_vendor_to_profile.assert_called_once_with(
        profileid, mac_addr, online_vendor
    )


def test_get_vendor_not_found(mocker, mock_db):
    ip_info = ModuleFactory().create_ip_info_obj(mock_db)
    mac_addr = "08:00:27:7f:09:e4"
    profileid = "profile_10.0.2.18"

    mock_db.get_mac_vendor_from_profile.return_value = None
    mocker.patch.object(ip_info, "get_vendor_offline", return_value=None)
    mocker.patch.object(ip_info, "get_vendor_online", return_value=None)

    result = ip_info.get_vendor(mac_addr, profileid)

    assert result == {"MAC": mac_addr, "Vendor": "Unknown"}
    (mock_db.get_mac_vendor_from_profile.assert_called_once_with(profileid))
    (ip_info.get_vendor_offline.assert_called_once_with(mac_addr, profileid))
    ip_info.get_vendor_online.assert_called_once_with(mac_addr)
    mock_db.set_mac_vendor_to_profile.assert_not_called()


def test_get_vendor_broadcast_mac(mocker, mock_db):
    ip_info = ModuleFactory().create_ip_info_obj(mock_db)
    mac_addr = "ff:ff:ff:ff:ff:ff"
    profileid = "profile_10.0.2.19"

    result = ip_info.get_vendor(mac_addr, profileid)

    assert result is False
    mock_db.get_mac_vendor_from_profile.assert_not_called()
    mocker.patch.object(ip_info, "get_vendor_offline").assert_not_called()
    mocker.patch.object(ip_info, "get_vendor_online").assert_not_called()
    mock_db.set_mac_vendor_to_profile.assert_not_called()


def test_get_age_no_creation_date(mock_db):
    domain = "example.com"

    mock_db.get_domain_data.return_value = None
    ip_info = ModuleFactory().create_ip_info_obj(mock_db)
    with patch("whois.query") as mock_whois:
        mock_whois.return_value = Mock(creation_date=None)

        result = ip_info.get_age(domain)

        assert result is False
        mock_db.set_info_for_domains.assert_not_called()


def test_get_age_invalid_tld(mock_db):
    domain = "example.invalid"
    ip_info = ModuleFactory().create_ip_info_obj(mock_db)
    result = ip_info.get_age(domain)

    assert result is False
    mock_db.get_domain_data.assert_not_called()
    mock_db.set_info_for_domains.assert_not_called()


def test_get_age_cached_data(mock_db):
    domain = "cached.com"
    cached_age = 100
    ip_info = ModuleFactory().create_ip_info_obj(mock_db)
    mock_db.get_domain_data.return_value = {"Age": cached_age}

    result = ip_info.get_age(domain)

    assert result is False
    mock_db.set_info_for_domains.assert_not_called()


@pytest.mark.parametrize("domain", ["example.arpa", "example.local"])
def test_get_age_special_domains(mock_db, domain):
    ip_info = ModuleFactory().create_ip_info_obj(mock_db)
    result = ip_info.get_age(domain)

    assert result is False
    mock_db.get_domain_data.assert_not_called()
    mock_db.set_info_for_domains.assert_not_called()


def test_get_rdns_valid_ip(mock_db):
    ip_info = ModuleFactory().create_ip_info_obj(mock_db)
    ip_address = "8.8.8.8"
    expected_rdns = {"reverse_dns": "dns.google"}

    with patch("socket.gethostbyaddr") as mock_gethostbyaddr, patch(
        "socket.inet_pton"
    ) as mock_inet_pton:

        mock_gethostbyaddr.return_value = ("dns.google", [], ["8.8.8.8"])
        mock_inet_pton.side_effect = socket.error

        result = ip_info.get_rdns(ip_address)
        assert result == expected_rdns

        mock_gethostbyaddr.assert_called_once_with(ip_address)
        mock_inet_pton.assert_called_once()
        mock_db.set_ip_info.assert_called_once_with(ip_address, expected_rdns)


def test_get_rdns_invalid_ip(mock_db):
    ip_info = ModuleFactory().create_ip_info_obj(mock_db)
    ip_address = "invalid_ip"

    with patch("socket.gethostbyaddr") as mock_gethostbyaddr:
        mock_gethostbyaddr.side_effect = socket.gaierror

        result = ip_info.get_rdns(ip_address)
        assert result is False

        mock_gethostbyaddr.assert_called_once_with(ip_address)


def test_get_rdns_no_reverse_dns(mock_db):
    ip_info = ModuleFactory().create_ip_info_obj(mock_db)
    ip_address = "1.1.1.1"

    with patch("socket.gethostbyaddr") as mock_gethostbyaddr, patch(
        "socket.inet_pton"
    ) as mock_inet_pton:

        mock_gethostbyaddr.return_value = ("1.1.1.1", [], ["1.1.1.1"])
        mock_inet_pton.return_value = b"\x01\x01\x01\x01"

        result = ip_info.get_rdns(ip_address)
        assert result is False

        mock_gethostbyaddr.assert_called_once_with(ip_address)
        mock_inet_pton.assert_called_once()


def test_get_rdns_localhost(mock_db):
    ip_info = ModuleFactory().create_ip_info_obj(mock_db)
    ip_address = "127.0.0.1"
    expected_rdns = {"reverse_dns": "localhost.localdomain"}

    with patch("socket.gethostbyaddr") as mock_gethostbyaddr, patch(
        "socket.inet_pton"
    ) as mock_inet_pton:

        mock_gethostbyaddr.return_value = (
            "localhost.localdomain",
            [],
            ["127.0.0.1"],
        )
        mock_inet_pton.side_effect = socket.error

        result = ip_info.get_rdns(ip_address)
        assert result == expected_rdns

        mock_gethostbyaddr.assert_called_once_with(ip_address)
        mock_inet_pton.assert_called_once()
        mock_db.set_ip_info.assert_called_once_with(ip_address, expected_rdns)


def test_set_evidence_malicious_jarm_hash(mocker, mock_db):
    ip_info = ModuleFactory().create_ip_info_obj(mock_db)
    flow = {
        "dport": 443,
        "daddr": "192.168.1.100",
        "saddr": "192.168.1.10",
        "starttime": 1625097600,
        "proto": "tcp",
        "uid": "CuTCcR1Bbp9Je7LVqa",
    }
    twid = "timewindow1"
    mock_db.get_port_info.return_value = "https"
    mock_db.get_ip_identification.return_value = "Known malicious server"
    mock_set_evidence = mocker.patch.object(ip_info.db, "set_evidence")
    ip_info.set_evidence_malicious_jarm_hash(flow, twid)
    assert mock_set_evidence.call_count == 2
    dst_evidence = mock_set_evidence.call_args_list[0][0][0]
    assert isinstance(dst_evidence, Evidence)
    assert dst_evidence.evidence_type == EvidenceType.MALICIOUS_JARM
    assert dst_evidence.attacker.direction == Direction.DST
    assert dst_evidence.attacker.attacker_type == IoCType.IP
    assert dst_evidence.attacker.value == "192.168.1.100"
    assert dst_evidence.threat_level == ThreatLevel.MEDIUM
    assert dst_evidence.confidence == 0.7
    assert "192.168.1.100" in dst_evidence.description
    assert "port: 443/tcp (HTTPS)" in dst_evidence.description
    assert "Known malicious server" in dst_evidence.description
    assert dst_evidence.profile.ip == "192.168.1.100"
    assert dst_evidence.timewindow.number == 1
    assert dst_evidence.uid == ["CuTCcR1Bbp9Je7LVqa"]
    assert dst_evidence.timestamp == 1625097600
    assert dst_evidence.category == IDEACategory.ANOMALY_TRAFFIC
    assert dst_evidence.proto == Proto.TCP
    assert dst_evidence.port == 443
    assert dst_evidence.source_target_tag == Tag.MALWARE
    src_evidence = mock_set_evidence.call_args_list[1][0][0]
    assert isinstance(src_evidence, Evidence)
    assert src_evidence.evidence_type == EvidenceType.MALICIOUS_JARM
    assert src_evidence.attacker.direction == Direction.SRC
    assert src_evidence.attacker.attacker_type == IoCType.IP
    assert src_evidence.attacker.value == "192.168.1.10"
    assert src_evidence.threat_level == ThreatLevel.LOW
    assert src_evidence.confidence == 0.7
    assert "192.168.1.100" in src_evidence.description
    assert "port: 443/tcp (HTTPS)" in src_evidence.description
    assert "Known malicious server" in src_evidence.description
    assert src_evidence.profile.ip == "192.168.1.10"
    assert src_evidence.timewindow.number == 1
    assert src_evidence.uid == ["CuTCcR1Bbp9Je7LVqa"]
    assert src_evidence.timestamp == 1625097600
    assert src_evidence.category == IDEACategory.ANOMALY_TRAFFIC
    assert src_evidence.proto == Proto.TCP
    assert src_evidence.port == 443
    assert src_evidence.source_target_tag == Tag.MALWARE


@pytest.mark.parametrize(
    "status_code, response_text, expected_vendor, " "mock_side_effect",
    [
        (
            200,
            "Valid Vendor",
            "Valid Vendor",
            None,
        ),
        (
            204,
            "",
            False,
            None,
        ),
        (
            None,
            None,
            False,
            requests.exceptions.ReadTimeout(),
        ),
        (
            None,
            None,
            False,
            requests.exceptions.ConnectionError(),
        ),
        (
            None,
            None,
            False,
            json.decoder.JSONDecodeError("Msg", "Doc", 0),
        ),
    ],
)
def test_get_vendor_online(
    mocker,
    mock_db,
    status_code,
    response_text,
    expected_vendor,
    mock_side_effect,
):
    ip_info = ModuleFactory().create_ip_info_obj(mock_db)
    mock_response = Mock(status_code=status_code, text=response_text)
    mock_requests = mocker.patch(
        "requests.get",
        return_value=mock_response,
        side_effect=mock_side_effect,
    )

    vendor = ip_info.get_vendor_online("00:11:22:33:44:55")

    assert vendor == expected_vendor
    mock_requests.assert_called_once_with(
        "https://api.macvendors.com/00:11:22:33:44:55", timeout=5
    )


def test_shutdown_gracefully(mocker, mock_db):
    ip_info = ModuleFactory().create_ip_info_obj(mock_db)

    mock_asn_db = mocker.Mock()
    mock_country_db = mocker.Mock()
    mock_mac_db = mocker.Mock()

    ip_info.asn_db = mock_asn_db
    ip_info.country_db = mock_country_db
    ip_info.mac_db = mock_mac_db

    ip_info.shutdown_gracefully()
    mock_asn_db.close.assert_called_once()
    mock_country_db.close.assert_called_once()
    mock_mac_db.close.assert_called_once()


@pytest.mark.parametrize(
    "platform_system, subprocess_output, expected_ip",
    [
        # Testcase 1: MacOS (Darwin) with valid output
        ("Darwin", b"gateway: 192.168.1.1", "192.168.1.1"),
        # Testcase 2: Linux with valid output
        ("Linux", b"default via 10.0.0.1 dev eth0", "10.0.0.1"),
        # Testcase 3: MacOS with invalid output
        ("Darwin", b"No default gateway", False),
        # Testcase 4: Unsupported OS
        ("Windows", b"", False),
    ],
)
def test_get_gateway_ip(
    mocker, mock_db, platform_system, subprocess_output, expected_ip
):
    ip_info = ModuleFactory().create_ip_info_obj(mock_db)
    mocker.patch("platform.system", return_value=platform_system)
    mocker.patch("subprocess.check_output", return_value=subprocess_output)
    mocker.patch("sys.argv", ["-i", "eth0"])
    result = ip_info.get_gateway_ip()
    assert result == expected_ip


@pytest.mark.parametrize(
    "ip, is_multicast, cached_info, expected_calls",
    [
        # Testcase 1: Valid IP, not multicast, no cached info
        (
            "192.168.1.1",
            False,
            {},
            {"get_geocountry": 1, "get_asn": 1, "get_rdns": 1},
        ),
        # Testcase 2: Valid IP, multicast
        ("224.0.0.1", True, {}, {}),
        # Testcase 3: Valid IP, not multicast,
        # with cached geocountry
        (
            "10.0.0.1",
            False,
            {"geocountry": "USA"},
            {"get_asn": 1, "get_rdns": 1},
        ),
    ],
)
def test_handle_new_ip(
    mocker, mock_db, ip, is_multicast, cached_info, expected_calls
):
    ip_info = ModuleFactory().create_ip_info_obj(mock_db)

    mock_ip_address = mocker.patch("ipaddress.ip_address")
    mock_ip_address.return_value.is_multicast = is_multicast

    mock_db.get_ip_info.return_value = cached_info

    mock_get_geocountry = mocker.patch.object(ip_info, "get_geocountry")
    mock_get_asn = mocker.patch.object(ip_info.asn, "get_asn")
    mock_get_rdns = mocker.patch.object(ip_info, "get_rdns")

    mocker.patch.object(ip_info.asn, "update_asn", return_value=True)
    ip_info.handle_new_ip(ip)
    assert mock_get_geocountry.call_count == expected_calls.get(
        "get_geocountry", 0
    )
    assert mock_get_asn.call_count == expected_calls.get("get_asn", 0)
    assert mock_get_rdns.call_count == expected_calls.get("get_rdns", 0)


def test_check_if_we_have_pending_mac_queries_with_mac_db(mocker, mock_db):
    ip_info = ModuleFactory().create_ip_info_obj(mock_db)
    ip_info.mac_db = Mock()
    ip_info.pending_mac_queries = Mock()
    ip_info.pending_mac_queries.empty.side_effect = [False, False, True]
    ip_info.pending_mac_queries.get.side_effect = [
        ("00:11:22:33:44:55", "profile_1"),
        ("AA:BB:CC:DD:EE:FF", "profile_2"),
        Exception("Empty queue"),
    ]
    mock_get_vendor = mocker.patch.object(ip_info, "get_vendor")
    ip_info.check_if_we_have_pending_mac_queries()
    assert mock_get_vendor.call_count == 2
    mock_get_vendor.assert_any_call("00:11:22:33:44:55", "profile_1")
    mock_get_vendor.assert_any_call("AA:BB:CC:DD:EE:FF", "profile_2")


def test_check_if_we_have_pending_mac_queries_empty_queue(mocker, mock_db):
    ip_info = ModuleFactory().create_ip_info_obj(mock_db)
    ip_info.mac_db = Mock()
    ip_info.pending_mac_queries = Mock()
    ip_info.pending_mac_queries.empty.return_value = True
    mock_get_vendor = mocker.patch.object(ip_info, "get_vendor")
    ip_info.check_if_we_have_pending_mac_queries()
    mock_get_vendor.assert_not_called()


def test_get_gateway_MAC_cached(mock_db):
    ip_info = ModuleFactory().create_ip_info_obj(mock_db)
    gw_ip = "192.168.1.1"
    cached_mac = "00:11:22:33:44:55"

    mock_db.get_mac_addr_from_profile.return_value = cached_mac

    result = ip_info.get_gateway_MAC(gw_ip)

    assert result == cached_mac
    mock_db.get_mac_addr_from_profile.assert_called_once_with(
        f"profile_{gw_ip}"
    )
    (mock_db.set_default_gateway.assert_called_once_with("MAC", cached_mac))


def test_get_gateway_MAC_arp_command(mocker, mock_db):
    ip_info = ModuleFactory().create_ip_info_obj(mock_db)
    gw_ip = "172.16.0.1"
    arp_output = "? (172.16.0.1) at 11:22:33:44:55:66 " "[ether] on eth0"
    expected_mac = "11:22:33:44:55:66"

    mock_db.get_mac_addr_from_profile.return_value = None
    mock_db.is_growing_zeek_dir.return_value = True

    mocker.patch("sys.argv", ["-i", "eth0"])

    mock_subprocess_run = mocker.patch("subprocess.run")
    mock_subprocess_run.side_effect = [
        subprocess.CalledProcessError(1, "cmd"),
        Mock(stdout=arp_output),
    ]

    result = ip_info.get_gateway_MAC(gw_ip)

    assert result == expected_mac
    assert mock_subprocess_run.call_count == 2
    mock_subprocess_run.assert_any_call(
        ["arp", "-an"], capture_output=True, check=True, text=True
    )
    (mock_db.set_default_gateway.assert_called_once_with("MAC", expected_mac))


def test_get_gateway_MAC_not_found(mocker, mock_db):
    ip_info = ModuleFactory().create_ip_info_obj(mock_db)
    gw_ip = "192.168.0.1"

    mock_db.get_mac_addr_from_profile.return_value = None
    mock_db.is_growing_zeek_dir.return_value = True

    mocker.patch("sys.argv", ["-i", "eth0"])

    mock_subprocess_run = mocker.patch("subprocess.run")
    mock_subprocess_run.side_effect = subprocess.CalledProcessError(1, "cmd")

    result = ip_info.get_gateway_MAC(gw_ip)

    assert result is None
    assert mock_subprocess_run.call_count == 2
    mock_db.set_default_gateway.assert_not_called()


def test_get_gateway_MAC_not_on_interface(mocker, mock_db):
    ip_info = ModuleFactory().create_ip_info_obj(mock_db)
    gw_ip = "192.168.1.1"

    mock_db.get_mac_addr_from_profile.return_value = None
    mock_db.is_growing_zeek_dir.return_value = False

    mocker.patch("sys.argv", [])

    mock_subprocess_run = mocker.patch("subprocess.run")

    result = ip_info.get_gateway_MAC(gw_ip)

    assert result is None
    mock_subprocess_run.assert_not_called()
    mock_db.set_default_gateway.assert_not_called()


def test_get_gateway_MAC_ip_command_success(mocker, mock_db):
    ip_info = ModuleFactory().create_ip_info_obj(mock_db)
    gw_ip = "10.0.0.1"
    ip_output = "10.0.0.1 dev eth0 lladdr aa:bb:cc:dd:ee:ff " "REACHABLE"
    expected_mac = "aa:bb:cc:dd:ee:ff"

    mock_db.get_mac_addr_from_profile.return_value = None
    mock_db.is_growing_zeek_dir.return_value = True

    mocker.patch("sys.argv", ["-i", "eth0"])

    mock_subprocess_run = mocker.patch("subprocess.run")
    mock_subprocess_run.return_value = Mock(stdout=ip_output)

    result = ip_info.get_gateway_MAC(gw_ip)

    assert result == expected_mac
    mock_subprocess_run.assert_called_once_with(
        ["ip", "neigh", "show", gw_ip],
        capture_output=True,
        check=True,
        text=True,
    )
    (mock_db.set_default_gateway.assert_called_once_with("MAC", expected_mac))


def test_get_gateway_MAC_ip_command_failure(mocker, mock_db):
    ip_info = ModuleFactory().create_ip_info_obj(mock_db)
    gw_ip = "172.16.0.1"

    mock_db.get_mac_addr_from_profile.return_value = None
    mock_db.is_growing_zeek_dir.return_value = True

    mocker.patch("sys.argv", ["-i", "eth0"])

    mock_subprocess_run = mocker.patch("subprocess.run")
    mock_subprocess_run.side_effect = [
        subprocess.CalledProcessError(1, "cmd"),
        subprocess.CalledProcessError(1, "cmd"),
    ]

    result = ip_info.get_gateway_MAC(gw_ip)

    assert result is None
    assert mock_subprocess_run.call_count == 2
    mock_subprocess_run.assert_any_call(
        ["ip", "neigh", "show", gw_ip],
        capture_output=True,
        check=True,
        text=True,
    )
    mock_subprocess_run.assert_any_call(
        ["arp", "-an"], capture_output=True, check=True, text=True
    )
    mock_db.set_default_gateway.assert_not_called()


@pytest.mark.parametrize(
    "ip_address, expected_family",
    [
        # Testcase 1: IPv4 address
        ("192.168.1.1", socket.AF_INET),
        # Testcase 2: IPv6 address
        ("2001:db8::1", socket.AF_INET6),
        # Testcase 3: Another IPv4 address
        ("10.0.0.1", socket.AF_INET),
        # Testcase 4: Another IPv6 address
        ("::1", socket.AF_INET6),
        # Testcase 5: IPv4-mapped IPv6 address
        ("::ffff:192.0.2.1", socket.AF_INET6),
    ],
)
def test_get_ip_family(mock_db, ip_address, expected_family):
    ip_info = ModuleFactory().create_ip_info_obj(mock_db)
    assert ip_info.get_ip_family(ip_address) == expected_family
