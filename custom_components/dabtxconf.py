#!/usr/bin/env python3
"""
DAB Modulator configuration tool.

Reverse-engineered from the device's own web UI (p_062000.js / p_064000.js /
p_066000.js). The config page is NOT a form-based CGI -- the browser reads a
222-byte binary struct straight out of an SPI flash sector, edits fields in
place as raw bytes, then erases and rewrites the whole sector:

    GET  b_070000   -> read current 8000-byte sector (first 222 bytes matter)
    GET  s_010000   -> status check (harmless, mirrors what the browser does)
    GET  e_070000   -> erase the sector at offset 0x070000
    POST _070000    -> write the modified 222-byte struct back
    GET  r_000000   -> restart the device so it reloads config from flash

This script replicates that exact sequence over HTTP Basic Auth so it can be
called from an external trigger (cron, webhook receiver, MQTT callback, etc.)
without touching a browser.

Usage examples
--------------
    # Just change frequency and amplitude, leave everything else untouched
    # (--user/--password default to "admin"/"admin" -- only needed if the
    # device login was changed from the factory default):
    python3 dab_modulator.py --host 10.3.75.2 \\
        --frequency 194064000 --amplitude 140 --restart

    # Device login has been changed -- pass current credentials for auth only,
    # this will NOT alter the stored login:
    python3 dab_modulator.py --host 10.3.75.2 --user opsuser --password s3cr3t \\
        --remote-ip 192.168.1.20 --remote-port 8000

Or import and call `apply_changes()` directly from your own trigger handler.
"""

import argparse
import sys
import time
import ipaddress
import requests
from requests.auth import HTTPBasicAuth

CFG_LEN = 222          # meaningful struct length (confirmed against captured POST)
SECTOR_OFFSET = "070000"

# byte53 <-> source crystal frequency (kHz), the two are always paired
SRC_FREQ_BY_BYTE53 = {
    0x64: 12288,   # 100
    0x40: 19200,   # 64
    0x32: 24576,   # 50
    0x28: 30720,   # 40
}


class ModulatorError(RuntimeError):
    pass


def _session(user: str, password: str) -> requests.Session:
    s = requests.Session()
    s.auth = HTTPBasicAuth(user, password)
    s.headers.update({"User-Agent": "dab-modulator-script/1.0"})
    return s


def read_config(session: requests.Session, base_url: str) -> bytearray:
    """GET b_070000 and return the first 222 meaningful bytes as a mutable array."""
    r = session.get(f"{base_url}/b_{SECTOR_OFFSET}", timeout=10)
    r.raise_for_status()
    data = r.content
    if len(data) < CFG_LEN:
        raise ModulatorError(f"Expected at least {CFG_LEN} bytes, got {len(data)}")
    return bytearray(data[:CFG_LEN])


def write_config(session: requests.Session, base_url: str, cfg: bytearray, restart: bool = False):
    """Erase the sector, write the new struct, optionally restart the device."""
    if len(cfg) != CFG_LEN:
        raise ModulatorError(f"Config struct must be exactly {CFG_LEN} bytes, got {len(cfg)}")

    # status check (mirrors setConfig() -> s_010000 before erase; non-fatal)
    try:
        session.get(f"{base_url}/s_010000", timeout=10)
    except requests.RequestException:
        pass

    r = session.get(f"{base_url}/e_{SECTOR_OFFSET}", timeout=10)
    r.raise_for_status()

    r = session.post(f"{base_url}/_{SECTOR_OFFSET}", data=bytes(cfg), timeout=10)
    r.raise_for_status()

    if restart:
        # give the flash write a moment to settle before triggering reload
        time.sleep(0.3)
        r = session.get(f"{base_url}/r_000000", timeout=10)
        r.raise_for_status()


# ---- field setters -----------------------------------------------------

def set_remote_ip(cfg: bytearray, ip: str):
    octets = [int(x) for x in ipaddress.IPv4Address(ip).packed]
    cfg[22:26] = octets


def set_remote_port(cfg: bytearray, port: int):
    if not (0 <= port <= 65535):
        raise ValueError("port must be 0-65535")
    cfg[26] = (port >> 8) & 0xFF
    cfg[27] = port & 0xFF


def set_amplitude(cfg: bytearray, value: int):
    if not (0 <= value <= 255):
        raise ValueError("amplitude must be 0-255")
    cfg[31] = value


def set_dac_current(cfg: bytearray, value: int):
    if not (0 <= value <= 255):
        raise ValueError("DAC current must be 0-255")
    cfg[48] = value


def set_frequency(cfg: bytearray, freq_hz: float):
    """
    Recomputes the 32-bit frequency tuning word at bytes 34-37 for a target
    output frequency in Hz, using the device's *current* source-clock byte
    (offset 53) so we don't disturb the oscillator/PLL selection -- only the
    tuning word changes.
    """
    byte53 = cfg[53]
    src_freq_khz = SRC_FREQ_BY_BYTE53.get(byte53)
    if src_freq_khz is None:
        raise ModulatorError(
            f"Unrecognized source-clock byte 0x{byte53:02X} at offset 53; "
            "refusing to guess the frequency formula."
        )

    # Inverse of:
    #   freq_hz = FTW * (src_freq_khz*1000*byte53/2) / 2**32
    ftw = round(freq_hz * (2 ** 33) / (src_freq_khz * 1000 * byte53))
    ftw &= 0xFFFFFFFF

    cfg[34] = (ftw >> 24) & 0xFF
    cfg[35] = (ftw >> 16) & 0xFF
    cfg[36] = (ftw >> 8) & 0xFF
    cfg[37] = ftw & 0xFF


def get_frequency(cfg: bytearray) -> float:
    """Inverse-free helper: read back the frequency currently encoded in cfg."""
    byte53 = cfg[53]
    src_freq_khz = SRC_FREQ_BY_BYTE53.get(byte53)
    if src_freq_khz is None:
        return float("nan")
    ftw = (cfg[34] << 24) | (cfg[35] << 16) | (cfg[36] << 8) | cfg[37]
    return ftw * (src_freq_khz * 1000 * byte53 / 2) / (2 ** 32)


# ---- high-level entry point --------------------------------------------

def apply_changes(host: str, user: str = "admin", password: str = "admin", *,
                   remote_ip=None, remote_port=None, frequency=None,
                   amplitude=None, dac_current=None, restart=False,
                   verify=True) -> dict:
    """
    Read the current config, apply only the fields that were passed, write it
    back. Returns a small summary dict for logging.

    `user`/`password` are used ONLY for the HTTP Basic Auth session -- they
    are never written into the config struct. If the device's login has been
    changed from the factory default (stored at offset 0x40, base64-encoded
    "user:password"), pass the current credentials here; this function will
    not alter them.
    """
    base_url = f"http://{host}"
    session = _session(user, password)

    cfg = read_config(session, base_url)
    before_freq = get_frequency(cfg)

    if remote_ip is not None:
        set_remote_ip(cfg, remote_ip)
    if remote_port is not None:
        set_remote_port(cfg, remote_port)
    if amplitude is not None:
        set_amplitude(cfg, amplitude)
    if dac_current is not None:
        set_dac_current(cfg, dac_current)
    if frequency is not None:
        set_frequency(cfg, frequency)

    write_config(session, base_url, cfg, restart=restart)

    summary = {
        "remote_ip": remote_ip,
        "remote_port": remote_port,
        "amplitude": amplitude,
        "dac_current": dac_current,
        "frequency_before_hz": before_freq,
        "frequency_after_hz": frequency if frequency is not None else before_freq,
        "restarted": restart,
    }

    if verify and restart:
        # optional read-back after restart to confirm it stuck
        time.sleep(1.0)
        try:
            cfg2 = read_config(session, base_url)
            summary["verified_frequency_hz"] = get_frequency(cfg2)
            summary["verified_amplitude"] = cfg2[31]
            summary["verified_dac_current"] = cfg2[48]
        except requests.RequestException as e:
            summary["verify_error"] = str(e)

    return summary


def main():
    p = argparse.ArgumentParser(description="Automate DAB modulator config changes")
    p.add_argument("--host", required=True, help="Modulator IP/hostname")
    p.add_argument("--user", default="admin",
                    help="HTTP Basic Auth username (auth only; default: admin). "
                         "Only needed if the device login was changed from default.")
    p.add_argument("--password", default="admin",
                    help="HTTP Basic Auth password (auth only; default: admin). "
                         "Only needed if the device login was changed from default.")
    p.add_argument("--remote-ip", help="ETI-server IP")
    p.add_argument("--remote-port", type=int, help="ETI-server port")
    p.add_argument("--frequency", type=float, help="Output frequency in Hz")
    p.add_argument("--amplitude", type=int, help="0-255")
    p.add_argument("--dac-current", type=int, help="0-255")
    p.add_argument("--restart", action="store_true",
                    help="Restart the device after writing so the change applies immediately")
    p.add_argument("--no-verify", action="store_true",
                    help="Skip post-restart read-back verification")
    args = p.parse_args()

    if not any([args.remote_ip, args.remote_port, args.frequency,
                args.amplitude is not None, args.dac_current is not None]):
        p.error("Provide at least one of --remote-ip / --remote-port / "
                 "--frequency / --amplitude / --dac-current")

    try:
        summary = apply_changes(
            args.host, args.user, args.password,
            remote_ip=args.remote_ip,
            remote_port=args.remote_port,
            frequency=args.frequency,
            amplitude=args.amplitude,
            dac_current=args.dac_current,
            restart=args.restart,
            verify=not args.no_verify,
        )
    except (requests.RequestException, ModulatorError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    for k, v in summary.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
