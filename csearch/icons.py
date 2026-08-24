"""文件类型 → 图标/颜色 映射，提升列表辨识度（Everything 风格）。"""

from __future__ import annotations

import flet as ft
from flet.controls.material.icons import Icons

# 扩展名 → (图标, 颜色) 映射表（按类别聚合，避免逐扩展名维护）
_EXT_MAP: dict[str, tuple[str, str]] = {}


def _reg(category: str, exts: list[str], icon: str, color: str) -> None:
    for e in exts:
        _EXT_MAP[e.lower()] = (icon, color)


_reg("image", ["jpg", "jpeg", "png", "gif", "bmp", "webp", "svg", "ico", "tif", "tiff",
               "heic", "raw", "psd", "ai", "avif"], Icons.IMAGE, "#34A853")
_reg("video", ["mp4", "mkv", "avi", "mov", "wmv", "flv", "webm", "m4v", "mpg", "mpeg",
               "3gp", "ts", "rmvb", "rm", "vob"], Icons.MOVIE, "#9334E6")
_reg("audio", ["mp3", "wav", "flac", "aac", "ogg", "wma", "m4a", "aiff", "ape", "mid",
               "midi", "opus", "amr"], Icons.MUSIC_NOTE, "#E91E63")
_reg("archive", ["zip", "rar", "7z", "tar", "gz", "bz2", "xz", "zst", "iso", "cab",
                 "jar", "war"], Icons.ARCHIVE, "#FB8C00")
_reg("doc", ["doc", "docx", "xls", "xlsx", "ppt", "pptx", "odt", "ods", "odp", "rtf",
             "pdf", "txt", "md", "json", "xml", "html", "htm", "csv", "log", "ini",
             "cfg", "conf", "yaml", "yml", "toml"], Icons.DESCRIPTION, "#4285F4")
_reg("code", ["py", "js", "ts", "java", "c", "cpp", "h", "cs", "go", "rs", "php", "rb",
              "sh", "bat", "ps1", "sql", "vue", "jsx", "tsx", "css", "scss", "lua",
              "swift", "kt", "dart"], Icons.CODE, "#5F6368")
_reg("exe", ["exe", "msi", "bat", "cmd", "com", "scr", "appx", "msix"], Icons.TERMINAL, "#37474F")


def icon_for(name: str, is_folder: bool) -> tuple[str, str]:
    """返回 (图标, 颜色)。文件夹优先，其次按扩展名，最后通用文件图标。"""
    if is_folder:
        return Icons.FOLDER, "#F9AB00"
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return _EXT_MAP.get(ext, (Icons.INSERT_DRIVE_FILE, "#9AA0A6"))


CATEGORY_ICONS: dict[str, str] = {
    "all": Icons.SEARCH,
    "folder": Icons.FOLDER,
    "doc": Icons.DESCRIPTION,
    "pic": Icons.IMAGE,
    "video": Icons.MOVIE,
    "audio": Icons.MUSIC_NOTE,
    "archive": Icons.ARCHIVE,
    "exe": Icons.TERMINAL,
}
