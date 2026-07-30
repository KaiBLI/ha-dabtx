"""Constants for the odrDAB TX Integration."""
from datetime import timedelta

DOMAIN = "hadabtx"

DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "admin"
DEFAULT_SCAN_INTERVAL = timedelta(seconds=30)

CFG_LEN = 222  # meaningful struct length inside the flash sector
SECTOR_OFFSET = "070000"

CONF_HOST = "host"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"

# byte53 <-> source crystal frequency (kHz); the two are always paired
SRC_FREQ_BY_BYTE53 = {
    0x64: 12288,  # 100
    0x40: 19200,  # 64
    0x32: 24576,  # 50
    0x28: 30720,  # 40
}

# DAB Band III block -> center frequency in Hz.
# NOTE: values were derived from a user-supplied CSV that was off by a
# factor of 10 (e.g. listed 7D as 19406400 Hz instead of the correct
# 194064000 Hz). These have been corrected to match published ETSI Band III
# block frequencies -- double check against your authoritative source
# before relying on this table operationally.
DAB_BLOCKS = {
    "5A": 174928000,
    "5B": 176640000,
    "5C": 178352000,
    "5D": 180064000,
    "6A": 181936000,
    "6B": 183648000,
    "6C": 185360000,
    "6D": 187072000,
    "7A": 188928000,
    "7B": 190640000,
    "7C": 192352000,
    "7D": 194064000,
    "8A": 195936000,
    "8B": 197648000,
    "8C": 199360000,
    "8D": 201072000,
    "9A": 202928000,
    "9B": 204640000,
    "9C": 206352000,
    "9D": 208064000,
    "10A": 209936000,
    "10B": 211648000,
    "10C": 213360000,
    "10D": 215072000,
    "10N": 210096000,
    "11A": 216928000,
    "11B": 218640000,
    "11C": 220352000,
    "11D": 222064000,
    "11N": 217088000,
    "12A": 223936000,
    "12B": 225648000,
    "12C": 227360000,
    "12D": 229072000,
    "12N": 224096000,
    "13A": 230784000,
    "13B": 232496000,
    "13C": 234208000,
    "13D": 235776000,
    "13E": 237488000,
    "13F": 239200000,
}

# reverse lookup for status reporting (Hz -> block), built at import time
HZ_TO_DAB_BLOCK = {hz: block for block, hz in DAB_BLOCKS.items()}

SERVICE_SET_CONFIG = "set_config"

ATTR_REMOTE_IP = "remote_ip"
ATTR_REMOTE_PORT = "remote_port"
ATTR_FREQUENCY_HZ = "frequency_hz"
ATTR_DAB_BLOCK = "dab_block"
ATTR_AMPLITUDE = "amplitude"
ATTR_DAC_CURRENT = "dac_current"
