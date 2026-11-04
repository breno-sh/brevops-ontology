"""Regras declaradas: literal -> tipo de unidade, janela de taxa, convenção de byte, nome, identificador."""
import pytest

from bo.units import rules as R


@pytest.mark.parametrize("lit,sentence,unit,window,bc", [
    ("GiB", "Size of created volumes in GiB.", "unit:GibiBYTE", None, "IEC"),
    ("KiB", "Record size, in kibibytes (KiB).", "unit:KibiBYTE", None, "IEC"),
    ("MiB", "Throughput that the EBS volume supports, in MiB/s.", "unit:MebiBYTE", "PT1S", "IEC"),
    ("Mbps", "Bandwidth in Mbps that determines the maximum bandwidth.", "unit:MegaBIT", "PT1S", "SI"),
    ("Gbps", "the capacity of the gateway spoke, in Gbps.", "unit:GigaBIT", "PT1S", "SI"),
    ("byte", "The size of the backup in bytes.", "unit:BYTE", None, "SI"),
    ("B", "Download size limit in Bytes.", "unit:BYTE", None, "SI"),
    ("gigabyte", "The size of the persistent storage in gigabytes (specifically GiB).", "unit:GibiBYTE", None, "IEC"),
    ("second", "Client keep alive value in seconds.", "unit:SEC", None, "NOT_APPLICABLE"),
    ("ms", "Custom timeout in milliseconds.", "unit:MilliSEC", None, "NOT_APPLICABLE"),
    ("us", "The maximum delay in microseconds.", "unit:MicroSEC", None, "NOT_APPLICABLE"),
    ("wk", "The lead time is in weeks.", "unit:WK", None, "NOT_APPLICABLE"),
    ("month", "For example 6 (months).", "unit:MO", None, "NOT_APPLICABLE"),
    ("%", "Flash Cache in percentage.", "unit:PERCENT", None, "NOT_APPLICABLE"),
    ("IOPS", "Amount of IOPS to provision for the disk.", "unit:NUM", "PT1S", "NOT_APPLICABLE"),
    ("OCPU", "The number of OCPUs.", "unit:NUM", None, "NOT_APPLICABLE"),
])
def test_literal_to_unit_type(lit, sentence, unit, window, bc):
    ut = R.literal_type(lit, sentence)
    assert ut is not None
    assert (ut.unit, ut.window, ut.bc) == (unit, window, bc)
    assert ut.qk == R.UNIT_KIND[unit]


@pytest.mark.parametrize("lit,sentence", [
    ("GB", "Disk size (GB) needed."),
    ("KB", "Maximum size (in KB) of any file."),
    ("terabyte", "Size of the data disk group, in terabytes (TBs)."),
])
def test_decimal_byte_prefix_is_ambiguous(lit, sentence):
    """GB sem a convenção declarada: grandeza AmountOfData, unidade UNKNOWN (nunca GigaBYTE por palpite)."""
    ut = R.literal_type(lit, sentence)
    assert ut.qk == R.DATA and ut.unit == R.UNK and ut.rule == "UNITS-BYTE-02"
    assert ut.bc == R.NA


def test_mbytes_per_second_from_sentence_case():
    ut = R.literal_type("Mbps", "Rate in MBps for the transfer.")
    assert ut.qk == R.DATA and ut.unit == R.UNK and ut.window == "PT1S"


def test_compound_unit_is_unknown():
    for lit, s in [("Mbps", "The throughput of the instance in MBps per TiB."),
                   ("gigabyte", "memory in gigabyte-seconds that your application may consume per day.")]:
        ut = R.literal_type(lit, s)
        assert (ut.qk, ut.unit) == (R.UNK, R.UNK) and ut.rule == "UNITS-RATE-02"


def test_rate_window_phrases():
    assert R.rate_window_in("10 per 5 minutes") == "PT5M"
    assert R.rate_window_in("per second") == "PT1S"
    assert R.rate_window_in("per hour") == "PT1H"
    assert R.rate_window_in("per day") == "P1D"
    assert R.rate_window_in("in KB/sec") == "PT1S"
    assert R.rate_window_in("one per secret") is None
    ut = R.literal_type("megabytes", "Bandwidth rate in megabytes per second, distributed.")
    assert ut.window == "PT1S" and ut.unit == R.UNK


def test_epoch_keeps_unit_and_marks_rule():
    ut = R.literal_type("second", "the date in seconds since the Unix epoch.")
    assert ut.unit == "unit:SEC" and ut.rule == "UNITS-EPOCH-01"


def test_unknown_literal_is_none():
    assert R.literal_type("parsecs", "") is None
    assert R.literal_type("", "") is None
    assert R.literal_type("b", "") is None   # 'b' sozinho não é byte


@pytest.mark.parametrize("name,unit,window", [
    ("timeout_in_seconds", "unit:SEC", None),
    ("retention_days", "unit:DAY", None),
    ("memory_mib", "unit:MebiBYTE", None),
    ("size_in_gb", R.UNK, None),
    ("max_content_size_in_mega_bytes", R.UNK, None),
    ("max_healthy_percentage", "unit:PERCENT", None),
    ("bandwidth_in_mbps", "unit:MegaBIT", "PT1S"),
    ("throughput_mibps", "unit:MebiBYTE", "PT1S"),
    ("storage_iops", "unit:NUM", "PT1S"),
    ("messages_per_second", "unit:NUM", "PT1S"),
    ("bytes_per_second", "unit:BYTE", "PT1S"),
    ("query_plans_per_minute", "unit:NUM", "PT1M"),
])
def test_name_rule(name, unit, window):
    ut = R.name_type(name)
    assert ut is not None and ut.rule == "UNITS-NAME-01"
    assert (ut.unit, ut.window) == (unit, window)


@pytest.mark.parametrize("name", ["ms", "gb", "sec", "replicas_min", "size", "count", "weight"])
def test_name_rule_does_not_guess(name):
    assert R.name_type(name) is None


def test_name_rule_skips_money_and_lone_nanos():
    assert R.name_type("amount.nanos", {"units", "currency_code"}) is None
    assert R.name_type("nanos", {"units"}) is None
    assert R.name_type("ttl.nanos", {"seconds"}).unit == "unit:NanoSEC"


def test_compound_name():
    assert R.name_compound("max_pods_per_node")
    assert R.name_compound("max_iops_per_tb")
    assert not R.name_compound("requests_per_second")


@pytest.mark.parametrize("name,expect", [
    ("from_port", True), ("port", True), ("priority", True), ("bgp_asn", True), ("vlan_id", True),
    ("icmp.code", True), ("code", False), ("rule_number", True), ("version", True),
    ("size", False), ("timeout", False), ("count", False),
])
def test_identifier_numbers(name, expect):
    assert R.is_identifier_number(name) is expect


def test_format_vocabulary_is_closed():
    assert R.format_of("ARN") == "arn"
    assert R.format_of("OCID") == "ocid"
    assert R.format_of("ISO-8601") == "iso8601"
    assert R.format_of({"aspect": "duration", "standard": "google.protobuf.Duration"}) == "protobuf_duration"
    assert R.format_of({"aspect": "identifier", "template": "{{name}}"}) is None
    assert R.format_of("whatever") is None


def test_every_unit_is_in_transforms_registry():
    from bo.transforms import units as tu
    assert set(R.UNIT_KIND) <= set(tu.UNITS)
    for u, conv in R.BYTE_CONV.items():
        reg = tu.UNITS[u].byte_convention
        assert reg in (None, conv)
