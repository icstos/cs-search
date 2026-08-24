"""文件类型 → 图标/颜色 映射（Everything 风格辨识度）。"""

from __future__ import annotations

import flet as ft
from flet.controls.material.icons import Icons

_EXT: dict[str, tuple[str, str]] = {}


def _reg(exts: list[str], icon: str, color: str) -> None:
    for e in exts:
        _EXT[e] = (icon, color)


_reg(["jpg", "jpeg", "png", "gif", "bmp", "webp", "svg", "ico", "tif", "tiff", "heic", "raw", "psd", "ai", "avif"],
     Icons.IMAGE, "#34A853")
_reg(["mp4", "mkv", "avi", "mov", "wmv", "flv", "webm", "m4v", "mpg", "mpeg", "3gp", "ts", "rmvb", "rm", "vob"],
     Icons.MOVIE, "#9334E6")
_reg(["mp3", "wav", "flac", "aac", "ogg", "wma", "m4a", "aiff", "ape", "mid", "midi", "opus", "amr"],
     Icons.MUSIC_NOTE, "#E91E63")
_reg(["zip", "rar", "7z", "tar", "gz", "bz2", "xz", "zst", "iso", "cab", "jar", "war"],
     Icons.ARCHIVE, "#FB8C00")
_reg(["doc", "docx", "xls", "xlsx", "ppt", "pptx", "odt", "ods", "odp", "rtf", "pdf", "txt", "md", "json", "xml",
      "html", "htm", "csv", "log", "ini", "cfg", "conf", "yaml", "yml", "toml"],
     Icons.DESCRIPTION, "#4285F4")
_reg(["py", "js", "ts", "java", "c", "cpp", "h", "cs", "go", "rs", "php", "rb", "sh", "bat", "ps1", "sql", "vue",
      "jsx", "tsx", "css", "scss", "lua", "swift", "kt", "dart"],
     Icons.CODE, "#5F6368")
_reg(["exe", "msi", "cmd", "com", "scr", "appx", "msix"], Icons.TERMINAL, "#37474F")


def icon_for(name: str, is_folder: bool) -> tuple[str, str]:
    if is_folder:
        return Icons.FOLDER, "#F9AB00"
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return _EXT.get(ext, (Icons.INSERT_DRIVE_FILE, "#9AA0A6"))


CATEGORY_ICONS: dict[str, str] = {
    "all": Icons.SEARCH, "folder": Icons.FOLDER, "doc": Icons.DESCRIPTION, "pic": Icons.IMAGE,
    "video": Icons.MOVIE, "audio": Icons.MUSIC_NOTE, "archive": Icons.ARCHIVE, "exe": Icons.TERMINAL,
}
