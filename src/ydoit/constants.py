"""Application-wide constants, paths, and defaults."""

from pathlib import Path

# --- Paths ---
CONFIG_DIR = Path.home() / ".config" / "ydoit"
DATA_FILE = CONFIG_DIR / "data.json.gpg"
BACKUP_SUFFIX = ".v1.bak"

# --- Identity ---
APP_ID = "org.ydoit.app"
APP_NAME = "ydoit"

# --- GNOME Keyring ---
KEYRING_SCHEMA_NAME = "org.ydoit.gpg-passphrase"
KEYRING_ATTRIBUTE = "application"
KEYRING_ATTRIBUTE_VALUE = "ydoit"
KEYRING_TIMESTAMP_ATTRIBUTE = "stored_at"

# --- GNOME Keybindings ---
MEDIA_KEYS_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys"
CUSTOM_KEYBINDING_SCHEMA = MEDIA_KEYS_SCHEMA + ".custom-keybinding"
CUSTOM_KEYBINDING_BASE = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings"
CUSTOM_KEYBINDING_KEY = "custom-keybindings"
YDOIT_SHORTCUT_PREFIX = "ydoit: "

# --- Defaults ---
DEFAULT_TYPING_DELAY_MS = 5
DEFAULT_HOLD_DELAY_MS = 5
DEFAULT_KEYRING_TIMEOUT_MIN = 15
DEFAULT_CATEGORY = "general"

# --- Input backends ---
# "auto" picks Mutter on remote-like GNOME sessions, else ydotool, else Mutter.
INPUT_BACKEND_AUTO = "auto"
INPUT_BACKEND_MUTTER = "mutter"
INPUT_BACKEND_YDOTOOL = "ydotool"
DEFAULT_INPUT_BACKEND = INPUT_BACKEND_AUTO
VALID_INPUT_BACKENDS = frozenset(
    {
        INPUT_BACKEND_AUTO,
        INPUT_BACKEND_MUTTER,
        INPUT_BACKEND_YDOTOOL,
    }
)
# Env var overrides persisted settings for one-shot debugging.
INPUT_BACKEND_ENV = "YDOIT_INPUT_BACKEND"

# --- Validation ---
ENTRY_TRIGGER_PATTERN = r"^[a-zA-Z0-9_-]+$"
MAX_ENTRY_TRIGGER_LENGTH = 64

# --- CLI exit codes ---
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_DECRYPTION_FAILED = 2
EXIT_YDOTOOL_NOT_RUNNING = 3
EXIT_ENTRY_NOT_FOUND = 4
EXIT_SHORTCUT_CONFLICT = 5

# --- Modifier key mappings (user-facing → GNOME dconf) ---
MODIFIER_TO_GNOME: dict[str, str] = {
    "Ctrl": "<Primary>",
    "Control": "<Primary>",
    "Alt": "<Alt>",
    "Shift": "<Shift>",
    "Super": "<Super>",
    "Meta": "<Super>",
}

GNOME_TO_MODIFIER: dict[str, str] = {
    "<Primary>": "Ctrl",
    "<Alt>": "Alt",
    "<Shift>": "Shift",
    "<Super>": "Super",
}
