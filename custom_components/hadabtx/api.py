"""Async client for the DAB modulator's flash-backed config interface.

Ported from the standalone dab_modulator.py script. See that script's
module docstring for a full explanation of the b_/e_/_/r_ endpoint scheme --
the short version is that the config page is not a form-based CGI, it's a
222-byte binary struct read straight out of an SPI flash sector, edited in
place, then erased and rewritten as a whole.
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging

import aiohttp

from .const import CFG_LEN, DAB_BLOCKS, HZ_TO_DAB_BLOCK, SECTOR_OFFSET, SRC_FREQ_BY_BYTE53

_LOGGER = logging.getLogger(__name__)


class DabModulatorError(Exception):
    """Raised for any modulator communication or protocol error."""


class DabModulatorClient:
    """Talks to a single DAB modulator over HTTP Basic Auth."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        username: str,
        password: str,
    ) -> None:
        self._session = session
        self._base_url = f"http://{host}"
        self._auth = aiohttp.BasicAuth(login=username, password=password)
        # This device's embedded HTTP stack can only handle one connection
        # at a time and will flat-out refuse a second one (rather than
        # queueing it). This lock ensures the coordinator's background poll
        # and any write sequence (which is itself several requests) never
        # overlap on the wire.
        self._lock = asyncio.Lock()

    async def _request(self, method: str, path: str, *, data: bytes | None = None,
                        retries: int = 3, retry_delay: float = 0.5):
        """
        Issue one request with a couple of retries for transient connection
        refusals -- the embedded stack sometimes isn't immediately ready to
        accept a new connection right after finishing the previous one, and
        is briefly unavailable while rebooting after a config write.
        """
        timeout = aiohttp.ClientTimeout(total=10)
        last_err: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                async with self._session.request(
                    method, f"{self._base_url}/{path}", auth=self._auth, data=data, timeout=timeout
                ) as resp:
                    resp.raise_for_status()
                    return await resp.read()
            except aiohttp.ClientError as err:
                last_err = err
                if attempt < retries:
                    await asyncio.sleep(retry_delay * attempt)
        raise DabModulatorError(f"{method} {path} failed after {retries} attempts: {last_err}") from last_err

    # ---- low-level flash sector access ---------------------------------

    async def _read_config(self) -> bytearray:
        data = await self._request("GET", f"b_{SECTOR_OFFSET}")
        if len(data) < CFG_LEN:
            raise DabModulatorError(f"Expected at least {CFG_LEN} bytes, got {len(data)}")
        return bytearray(data[:CFG_LEN])

    async def _write_config(self, cfg: bytearray) -> None:
        if len(cfg) != CFG_LEN:
            raise DabModulatorError(f"Config struct must be exactly {CFG_LEN} bytes, got {len(cfg)}")

        # status check (mirrors the browser's setConfig() flow; non-fatal)
        try:
            await self._request("GET", "s_010000", retries=1)
        except DabModulatorError:
            pass

        await self._request("GET", f"e_{SECTOR_OFFSET}")
        await self._request("POST", f"_{SECTOR_OFFSET}", data=bytes(cfg))

        # a reboot is required for changes to take effect on this hardware;
        # give the write a moment to settle, then expect the device to be
        # briefly unreachable while it restarts -- retries absorb that.
        await asyncio.sleep(0.3)
        await self._request("GET", "r_000000", retries=5, retry_delay=1.0)

    # ---- field decode/encode helpers (offsets match the flash struct) --

    @staticmethod
    def _get_remote_ip(cfg: bytearray) -> str:
        return str(ipaddress.IPv4Address(bytes(cfg[22:26])))

    @staticmethod
    def _set_remote_ip(cfg: bytearray, ip: str) -> None:
        cfg[22:26] = ipaddress.IPv4Address(ip).packed

    @staticmethod
    def _get_remote_port(cfg: bytearray) -> int:
        return (cfg[26] << 8) | cfg[27]

    @staticmethod
    def _set_remote_port(cfg: bytearray, port: int) -> None:
        if not (0 <= port <= 65535):
            raise ValueError("port must be 0-65535")
        cfg[26] = (port >> 8) & 0xFF
        cfg[27] = port & 0xFF

    @staticmethod
    def _get_amplitude(cfg: bytearray) -> int:
        return cfg[31]

    @staticmethod
    def _set_amplitude(cfg: bytearray, value: int) -> None:
        if not (0 <= value <= 255):
            raise ValueError("amplitude must be 0-255")
        cfg[31] = value

    @staticmethod
    def _get_dac_current(cfg: bytearray) -> int:
        return cfg[48]

    @staticmethod
    def _set_dac_current(cfg: bytearray, value: int) -> None:
        if not (0 <= value <= 255):
            raise ValueError("DAC current must be 0-255")
        cfg[48] = value

    @staticmethod
    def _get_frequency(cfg: bytearray) -> float:
        byte53 = cfg[53]
        src_freq_khz = SRC_FREQ_BY_BYTE53.get(byte53)
        if src_freq_khz is None:
            return float("nan")
        ftw = (cfg[34] << 24) | (cfg[35] << 16) | (cfg[36] << 8) | cfg[37]
        return ftw * (src_freq_khz * 1000 * byte53 / 2) / (2 ** 32)

    @staticmethod
    def _set_frequency(cfg: bytearray, freq_hz: float) -> None:
        byte53 = cfg[53]
        src_freq_khz = SRC_FREQ_BY_BYTE53.get(byte53)
        if src_freq_khz is None:
            raise DabModulatorError(
                f"Unrecognized source-clock byte 0x{byte53:02X} at offset 53; "
                "refusing to guess the frequency formula."
            )
        ftw = round(freq_hz * (2 ** 33) / (src_freq_khz * 1000 * byte53))
        ftw &= 0xFFFFFFFF
        cfg[34] = (ftw >> 24) & 0xFF
        cfg[35] = (ftw >> 16) & 0xFF
        cfg[36] = (ftw >> 8) & 0xFF
        cfg[37] = ftw & 0xFF

    @staticmethod
    def _set_connection_mode(cfg: bytearray, mode: str) -> None:
        mapping = {"server": 0x02, "client": 0x04, "off": 0x10}
        if mode not in mapping:
            raise DabModulatorError(f"Invalid connection_mode '{mode}'; must be one of {sorted(mapping)}")
        cfg[28] = mapping[mode]

    @staticmethod
    def _get_connection_mode(cfg: bytearray) -> str:
        byte28 = cfg[28]
        if byte28 == 0x02:
            return "server"
        if byte28 == 0x04:
            return "client"
        if byte28 == 0x10:
            return "off"
        return "unknown"

    @staticmethod
    def _parse_live_status(data: bytes) -> dict:
        """
        Decode the 14-byte live status block (GET s_000000). This is
        separate from the flash config struct -- it reflects the device's
        current runtime state, not stored settings.
        """
        if len(data) < 14:
            raise DabModulatorError(f"Expected at least 14 bytes from status read, got {len(data)}")

        # RF frontend (byte 4)
        fe = data[4]
        if (fe & 0x50) != 0:
            rf_frontend_active = False
            rf_frontend_status = "Off"
        elif fe == 0x02:
            rf_frontend_active = True
            rf_frontend_status = "Active"
        else:
            rf_frontend_active = False
            rf_frontend_status = f"Unknown (0x{fe:02X})"

        # Network/ETI connection state (bytes 9-11)
        b9, b10, b11 = data[9], data[10], data[11]
        if b9 in (0x02, 0x04) and b11 == 0x17:
            connection_state = "Connected"
            eti_socket_on = True
        elif b9 in (0x00, 0x01):
            eti_socket_on = False
            connection_state = "Admin Off" if b10 == 0x01 else "Flash Off"
        elif b9 == 0x02 and b11 == 0x14:
            connection_state = "Listening"
            eti_socket_on = True
        elif b9 == 0x04 and b11 in (0x13, 0x00):
            connection_state = "Connecting"
            eti_socket_on = True
        else:
            connection_state = f"Unknown (0x{b9:02X}:0x{b10:02X}:0x{b11:02X})"
            eti_socket_on = False

        flags = data[13]
        if flags & 0x01:
            ifft_overflow = "Active"
        elif flags & 0x04:
            ifft_overflow = "Happened"
        else:
            ifft_overflow = "OK"

        if flags & 0x02:
            fir_clipped = "Active"
        elif flags & 0x08:
            fir_clipped = "Happened"
        else:
            fir_clipped = "OK"

        return {
            "rf_frontend_active": rf_frontend_active,
            "rf_frontend_status": rf_frontend_status,
            "connection_state": connection_state,
            "eti_socket_on": eti_socket_on,
            "ifft_overflow": ifft_overflow,
            "fir_clipped": fir_clipped,
            "sram_detected": bool(flags & 0x80),
            "broadcasting": bool(flags & 0x40),
            "buffer_fullness_pct": round(data[12] * 100 / 255),
        }

    # ---- public API ------------------------------------------------------

    async def async_get_status(self) -> dict:
        """Read current status from the modulator for sensors/coordinator."""
        async with self._lock:
            cfg = await self._read_config()
            live_raw = await self._request("GET", "s_000000")

        freq_hz = self._get_frequency(cfg)
        status = {
            "remote_ip": self._get_remote_ip(cfg),
            "remote_port": self._get_remote_port(cfg),
            "amplitude": self._get_amplitude(cfg),
            "dac_current": self._get_dac_current(cfg),
            "frequency_hz": freq_hz,
            "dab_block": HZ_TO_DAB_BLOCK.get(round(freq_hz)),
            "connection_mode": self._get_connection_mode(cfg),
        }
        status.update(self._parse_live_status(live_raw))
        return status

    async def async_set_rf_frontend(self, turn_on: bool) -> None:
        """
        Immediately enable/disable the RF frontend. This is a live action
        endpoint, separate from the flash config struct -- no erase, write,
        or reboot involved, so it takes effect right away.
        """
        path = "s_020000" if turn_on else "s_025000"
        async with self._lock:
            await self._request("GET", path)

    async def async_set_eti_socket(self, turn_on: bool) -> None:
        """
        Immediately enable/disable the ETI socket. Also a live action, no
        reboot required. Turning it on needs to know whether the device is
        configured as a TCP server or client (from the flash config), so
        this does one quick config read first.
        """
        async with self._lock:
            if turn_on:
                cfg = await self._read_config()
                mode = self._get_connection_mode(cfg)
                if mode == "server":
                    path = "s_010200"
                elif mode == "client":
                    path = "s_010400"
                else:
                    raise DabModulatorError(
                        "Cannot enable the ETI socket: the device's connection "
                        "mode isn't set to server or client. Set connection_mode "
                        "to 'server' or 'client' via set_config first."
                    )
            else:
                path = "s_010000"
            await self._request("GET", path)

    async def async_apply_changes(
        self,
        *,
        remote_ip: str | None = None,
        remote_port: int | None = None,
        frequency_hz: float | None = None,
        dab_block: str | None = None,
        amplitude: int | None = None,
        dac_current: int | None = None,
        connection_mode: str | None = None,
    ) -> dict:
        """
        Read the current config, apply only the fields that were passed,
        write it back, and restart the device (a reboot is required on this
        hardware for changes to take effect). Returns the resulting status.
        """
        if frequency_hz is not None and dab_block is not None:
            raise DabModulatorError("Specify either frequency_hz or dab_block, not both")

        if connection_mode is not None:
                self._set_connection_mode(cfg, connection_mode)

        if dab_block is not None:
            block = dab_block.strip().upper()
            if block not in DAB_BLOCKS:
                raise DabModulatorError(
                    f"Unknown DAB block '{dab_block}'. Known blocks: {', '.join(sorted(DAB_BLOCKS))}"
                )
            frequency_hz = DAB_BLOCKS[block]

        async with self._lock:
            cfg = await self._read_config()

            if remote_ip is not None:
                self._set_remote_ip(cfg, remote_ip)
            if remote_port is not None:
                self._set_remote_port(cfg, remote_port)
            if amplitude is not None:
                self._set_amplitude(cfg, amplitude)
            if dac_current is not None:
                self._set_dac_current(cfg, dac_current)
            if frequency_hz is not None:
                self._set_frequency(cfg, frequency_hz)

            await self._write_config(cfg)

        # give the reboot a moment before reading back for confirmation
        # (async_get_status() acquires the lock itself -- kept outside the
        # block above so we don't try to re-enter a non-reentrant lock)
        await asyncio.sleep(1.0)
        return await self.async_get_status()
