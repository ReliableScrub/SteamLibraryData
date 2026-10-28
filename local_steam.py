import json
import re
import struct
import sys
from pathlib import Path

STEAM_ID64_BASE = 76561197960265728
APPINFO_V41_MAGIC = 0x07564429
APPINFO_FIXED_BYTES = 60

LOCAL_APP_TYPE_MAP = {
    "game": "game",
    "software": "software",
    "dlc": "dlc",
    "video": "video",
    "hardware": "hardware",
    "beta": "test",
}


class AppInfoError(RuntimeError):
    pass


def find_steam_directory(explicit=None):
    candidates = []

    if explicit:
        path = Path(explicit).expanduser()
        candidates.append(
            path.parent.parent if path.name.casefold() == "appinfo.vdf" else path
        )

    if sys.platform == "win32":
        try:
            import winreg

            registry_locations = (
                (
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Valve\Steam",
                    "SteamPath",
                ),
                (
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\WOW6432Node\Valve\Steam",
                    "InstallPath",
                ),
                (
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\Valve\Steam",
                    "InstallPath",
                ),
            )

            for hive, key_name, value_name in registry_locations:
                try:
                    with winreg.OpenKey(hive, key_name) as key:
                        value, _ = winreg.QueryValueEx(key, value_name)

                    candidates.append(Path(value))

                except OSError:
                    pass

        except ImportError:
            pass

        candidates.extend(
            [
                Path(r"C:\Program Files (x86)\Steam"),
                Path(r"C:\Program Files\Steam"),
            ]
        )

    elif sys.platform == "darwin":
        candidates.append(Path.home() / "Library" / "Application Support" / "Steam")

    else:
        candidates.extend(
            [
                Path.home() / ".steam" / "steam",
                Path.home() / ".local" / "share" / "Steam",
                (
                    Path.home()
                    / ".var"
                    / "app"
                    / "com.valvesoftware.Steam"
                    / "data"
                    / "Steam"
                ),
            ]
        )

    seen = set()

    for path in candidates:
        try:
            path = path.resolve()

        except OSError:
            continue

        if path in seen:
            continue

        seen.add(path)

        if path.is_dir() and (path / "userdata").is_dir():
            return path

    return None


def steam_account_id(steam_id):
    try:
        account_id = int(str(steam_id).strip()) - STEAM_ID64_BASE

    except (TypeError, ValueError):
        return None

    return account_id if account_id > 0 else None


def get_user_config_directory(steam_id, steam_dir=None):
    steam_dir = steam_dir or find_steam_directory()

    if steam_dir is None:
        return None

    account_id = steam_account_id(steam_id)

    if account_id is None:
        return None

    config_dir = Path(steam_dir) / "userdata" / str(account_id) / "config"

    return config_dir if config_dir.is_dir() else None


def get_private_app_ids(steam_id, steam_dir=None):
    config_dir = get_user_config_directory(
        steam_id,
        steam_dir=steam_dir,
    )

    if config_dir is None:
        return None

    account_id = steam_account_id(steam_id)
    path = config_dir / "localconfig.vdf"

    try:
        text = path.read_text(
            encoding="utf-8",
            errors="replace",
        )

    except OSError:
        return None

    match = re.search(
        rf'"PrivateApps_{account_id}"\s*"([^"]*)"',
        text,
        re.IGNORECASE,
    )

    if match is None:
        return set()

    try:
        values = json.loads(match.group(1))

    except (TypeError, ValueError):
        return None

    if not isinstance(values, list):
        return None

    private_app_ids = set()

    for value in values:
        try:
            app_id = int(value)

        except (TypeError, ValueError):
            continue

        if app_id > 0:
            private_app_ids.add(app_id)

    return private_app_ids


def get_local_achievement_progress(
    steam_id,
    app_id,
    steam_dir=None,
):
    if not isinstance(app_id, int) or app_id <= 0:
        return None

    config_dir = get_user_config_directory(
        steam_id,
        steam_dir=steam_dir,
    )

    if config_dir is None:
        return None

    path = config_dir / "librarycache" / f"{app_id}.json"

    try:
        payload = json.loads(
            path.read_text(
                encoding="utf-8",
                errors="replace",
            )
        )

    except (OSError, ValueError):
        return None

    if not isinstance(payload, list):
        return None

    data = None

    for item in payload:
        if (
            isinstance(item, list)
            and len(item) >= 2
            and item[0] == "achievements"
            and isinstance(item[1], dict)
        ):
            candidate = item[1].get("data")

            data = candidate if isinstance(candidate, dict) else None

            break

    if data is None:
        return None

    total = data.get("nTotal")
    unlocked = data.get("nAchieved")

    if not isinstance(total, int) or isinstance(total, bool) or total < 0:
        return None

    if (
        not isinstance(unlocked, int)
        or isinstance(unlocked, bool)
        or unlocked < 0
        or unlocked > total
    ):
        return None

    return total, unlocked


def _read_exact(file, size, what):
    data = file.read(size)

    if len(data) != size:
        raise AppInfoError(f"Unexpected EOF while reading {what}.")

    return data


def _read_string_table(file, offset):
    file.seek(offset)

    count = struct.unpack(
        "<I",
        _read_exact(
            file,
            4,
            "string-table count",
        ),
    )[0]

    table = []

    for _ in range(count):
        buffer = bytearray()

        while True:
            byte = _read_exact(
                file,
                1,
                "string-table string",
            )

            if byte == b"\x00":
                break

            buffer += byte

        table.append(
            buffer.decode(
                "utf-8",
                errors="replace",
            )
        )

    return table


def _read_cstring(data, position):
    end = data.find(
        b"\x00",
        position,
    )

    if end < 0:
        raise AppInfoError("Unterminated UTF-8 string in binary VDF.")

    return (
        data[position:end].decode(
            "utf-8",
            errors="replace",
        ),
        end + 1,
    )


def _read_wstring(data, position):
    end = position

    while end + 1 < len(data):
        if data[end : end + 2] == b"\x00\x00":
            return (
                data[position:end].decode(
                    "utf-16-le",
                    errors="replace",
                ),
                end + 2,
            )

        end += 2

    raise AppInfoError("Unterminated UTF-16 string in binary VDF.")


def _read_number(data, position, format_string):
    size = struct.calcsize(format_string)

    if position + size > len(data):
        raise AppInfoError("Unexpected EOF while reading binary VDF value.")

    return (
        struct.unpack_from(
            format_string,
            data,
            position,
        )[0],
        position + size,
    )


def _parse_binary_vdf(
    data,
    string_table,
    position=0,
    depth=0,
):
    if depth > 64:
        raise AppInfoError("Binary VDF nesting is unexpectedly deep.")

    result = {}

    while position < len(data):
        value_type = data[position]
        position += 1

        if value_type == 0x08:
            return result, position

        key_index, position = _read_number(
            data,
            position,
            "<I",
        )

        if key_index >= len(string_table):
            raise AppInfoError(
                f"Binary VDF key index {key_index} exceeds the string table."
            )

        key = string_table[key_index]

        if value_type == 0x00:
            value, position = _parse_binary_vdf(
                data,
                string_table,
                position,
                depth + 1,
            )

        elif value_type == 0x01:
            value, position = _read_cstring(
                data,
                position,
            )

        elif value_type == 0x02:
            value, position = _read_number(
                data,
                position,
                "<i",
            )

        elif value_type == 0x03:
            value, position = _read_number(
                data,
                position,
                "<f",
            )

        elif value_type in (0x04, 0x06):
            value, position = _read_number(
                data,
                position,
                "<I",
            )

        elif value_type == 0x05:
            value, position = _read_wstring(
                data,
                position,
            )

        elif value_type == 0x07:
            value, position = _read_number(
                data,
                position,
                "<Q",
            )

        else:
            raise AppInfoError(f"Unsupported binary VDF type 0x{value_type:02X}.")

        result[key] = value

    return result, position


def _find_common_section(value):
    if not isinstance(value, dict):
        return None

    common = value.get("common")

    if isinstance(common, dict):
        return common

    for child in value.values():
        result = _find_common_section(child)

        if result is not None:
            return result

    return None


def _read_appinfo_types(path, target_app_ids):
    target_app_ids = {
        app_id for app_id in target_app_ids if isinstance(app_id, int) and app_id > 0
    }

    if not target_app_ids:
        return {}

    file_size = path.stat().st_size
    raw_types = {}

    with path.open("rb") as file:
        magic, _, string_table_offset = struct.unpack(
            "<IIQ",
            _read_exact(
                file,
                16,
                "appinfo header",
            ),
        )

        if magic != APPINFO_V41_MAGIC:
            raise AppInfoError(
                "Unsupported appinfo.vdf format. "
                f"Expected v41 magic "
                f"0x{APPINFO_V41_MAGIC:08X}, "
                f"found 0x{magic:08X}."
            )

        if not (16 < string_table_offset <= file_size):
            raise AppInfoError("Invalid appinfo.vdf string-table offset.")

        string_table = _read_string_table(
            file,
            string_table_offset,
        )

        file.seek(16)

        while file.tell() + 4 <= string_table_offset:
            app_id = struct.unpack(
                "<I",
                _read_exact(
                    file,
                    4,
                    "AppID",
                ),
            )[0]

            if app_id == 0:
                break

            entry_size = struct.unpack(
                "<I",
                _read_exact(
                    file,
                    4,
                    "entry size",
                ),
            )[0]

            entry_end = file.tell() + entry_size

            if entry_size < APPINFO_FIXED_BYTES or entry_end > string_table_offset:
                raise AppInfoError(
                    f"Invalid appinfo.vdf entry size for AppID {app_id}."
                )

            if app_id not in target_app_ids:
                file.seek(entry_end)
                continue

            entry = _read_exact(
                file,
                entry_size,
                f"AppID {app_id}",
            )

            try:
                root, _ = _parse_binary_vdf(
                    entry[APPINFO_FIXED_BYTES:],
                    string_table,
                )

                common = _find_common_section(root) or {}

                raw_type = common.get("type")

                if raw_type is not None:
                    raw_types[app_id] = str(raw_type).strip()

            except AppInfoError:
                continue

            if len(raw_types) == len(target_app_ids):
                break

    return raw_types


def get_local_app_types(
    app_ids,
    steam_dir=None,
):
    steam_dir = steam_dir or find_steam_directory()

    if steam_dir is None:
        return {}

    path = Path(steam_dir) / "appcache" / "appinfo.vdf"

    if not path.is_file():
        return {}

    try:
        raw_types = _read_appinfo_types(
            path,
            app_ids,
        )

    except (OSError, AppInfoError):
        return {}

    classifications = {}

    for app_id, raw_type in raw_types.items():
        normalized = LOCAL_APP_TYPE_MAP.get(raw_type.casefold())

        if normalized is not None:
            classifications[app_id] = normalized

    return classifications
