"""Reading the AC standby timeout (output is localized, so parse only the numbers)."""
import re

QUERY_STANDBY = ["powercfg", "/query", "SCHEME_CURRENT", "SUB_SLEEP", "STANDBYIDLE"]
_HEX = re.compile(r"0x[0-9a-fA-F]{8}")


def parse_ac_standby_minutes(output: str | None) -> int | None:
    """AC standby timeout in minutes from `powercfg /query` output, else None.

    The last two hex values in the output are always the current AC then DC
    setting indexes (in seconds), whatever language Windows is in.
    """
    values = _HEX.findall(output or "")
    if len(values) < 2:
        return None
    return int(values[-2], 16) // 60
