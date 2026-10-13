"""File-type knowledge: Markdown fence languages, binary extensions, secrets.

Everything in here is deliberately data-only.  Keeping the tables in one
module makes them easy to audit and easy for contributors to extend.
"""

from __future__ import annotations

import os
from collections.abc import Iterable

# --------------------------------------------------------------------------
# Language detection (used for Markdown code fences)
# --------------------------------------------------------------------------

EXTENSION_LANGUAGES = {
    # Python & friends
    ".py": "python",
    ".pyi": "python",
    ".pyx": "cython",
    ".pxd": "cython",
    ".ipynb": "json",
    # JavaScript / TypeScript
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "jsx",
    ".ts": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".tsx": "tsx",
    ".vue": "vue",
    ".svelte": "svelte",
    ".astro": "astro",
    # JVM & .NET
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".scala": "scala",
    ".groovy": "groovy",
    ".gradle": "groovy",
    ".cs": "csharp",
    ".fs": "fsharp",
    ".vb": "vbnet",
    # Systems
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".hxx": "cpp",
    ".m": "objective-c",
    ".mm": "objective-cpp",
    ".go": "go",
    ".rs": "rust",
    ".swift": "swift",
    ".dart": "dart",
    ".zig": "zig",
    ".nim": "nim",
    ".v": "verilog",
    ".sv": "systemverilog",
    ".vhd": "vhdl",
    ".asm": "asm",
    ".s": "asm",
    # Dynamic languages
    ".rb": "ruby",
    ".rake": "ruby",
    ".php": "php",
    ".pl": "perl",
    ".pm": "perl",
    ".lua": "lua",
    ".r": "r",
    ".jl": "julia",
    ".ex": "elixir",
    ".exs": "elixir",
    ".erl": "erlang",
    ".hrl": "erlang",
    ".hs": "haskell",
    ".ml": "ocaml",
    ".mli": "ocaml",
    ".clj": "clojure",
    ".cljs": "clojure",
    ".elm": "elm",
    ".tcl": "tcl",
    # Shells
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "zsh",
    ".fish": "fish",
    ".ps1": "powershell",
    ".psm1": "powershell",
    ".psd1": "powershell",
    ".bat": "batch",
    ".cmd": "batch",
    # Data & config
    ".sql": "sql",
    ".graphql": "graphql",
    ".gql": "graphql",
    ".proto": "protobuf",
    ".thrift": "thrift",
    ".json": "json",
    ".jsonc": "jsonc",
    ".json5": "json5",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".ini": "ini",
    ".cfg": "ini",
    ".conf": "ini",
    ".env": "dotenv",
    ".properties": "properties",
    ".xml": "xml",
    ".xsl": "xml",
    ".xsd": "xml",
    ".plist": "xml",
    ".svg": "xml",
    ".tf": "hcl",
    ".tfvars": "hcl",
    ".hcl": "hcl",
    ".cmake": "cmake",
    ".mk": "makefile",
    ".make": "makefile",
    ".nix": "nix",
    ".csv": "csv",
    ".tsv": "tsv",
    # Docs
    ".md": "markdown",
    ".markdown": "markdown",
    ".mdx": "mdx",
    ".rst": "rst",
    ".adoc": "asciidoc",
    ".tex": "latex",
    ".bib": "bibtex",
    ".txt": "text",
    ".log": "text",
    ".diff": "diff",
    ".patch": "diff",
    # Misc markup
    ".html": "html",
    ".htm": "html",
    ".xhtml": "html",
    ".css": "css",
    ".scss": "scss",
    ".sass": "sass",
    ".less": "less",
    ".styl": "stylus",
}

FILENAME_LANGUAGES = {
    "dockerfile": "dockerfile",
    "containerfile": "dockerfile",
    "makefile": "makefile",
    "gnumakefile": "makefile",
    "justfile": "makefile",
    "cmakelists.txt": "cmake",
    "gemfile": "ruby",
    "rakefile": "ruby",
    "vagrantfile": "ruby",
    "procfile": "text",
    "codeowners": "text",
    ".gitignore": "gitignore",
    ".dockerignore": "gitignore",
    ".npmignore": "gitignore",
    ".eslintignore": "gitignore",
    ".prettierignore": "gitignore",
    ".packdiffignore": "gitignore",
    ".gitattributes": "gitattributes",
    ".editorconfig": "ini",
    ".env.example": "dotenv",
    ".env.sample": "dotenv",
    ".env.template": "dotenv",
}

# --------------------------------------------------------------------------
# Binary extensions — never worth pasting into a prompt
# --------------------------------------------------------------------------

BINARY_EXTENSIONS = frozenset(
    {
        # images
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".bmp",
        ".tif",
        ".tiff",
        ".webp",
        ".ico",
        ".icns",
        ".heic",
        ".avif",
        ".psd",
        ".ai",
        ".eps",
        ".raw",
        ".cr2",
        ".nef",
        # audio
        ".mp3",
        ".wav",
        ".flac",
        ".ogg",
        ".oga",
        ".m4a",
        ".aac",
        ".wma",
        ".opus",
        ".mid",
        ".midi",
        # video
        ".mp4",
        ".m4v",
        ".avi",
        ".mov",
        ".mkv",
        ".webm",
        ".wmv",
        ".flv",
        ".mpg",
        ".mpeg",
        ".3gp",
        # archives & packages
        ".zip",
        ".tar",
        ".gz",
        ".tgz",
        ".bz2",
        ".xz",
        ".7z",
        ".rar",
        ".zst",
        ".lz",
        ".lzma",
        ".jar",
        ".war",
        ".ear",
        ".whl",
        ".egg",
        ".apk",
        ".aab",
        ".ipa",
        ".deb",
        ".rpm",
        ".dmg",
        ".iso",
        ".img",
        ".cab",
        ".msi",
        ".nupkg",
        ".snap",
        ".flatpak",
        # executables & objects
        ".exe",
        ".dll",
        ".so",
        ".dylib",
        ".bin",
        ".o",
        ".a",
        ".obj",
        ".lib",
        ".class",
        ".pyc",
        ".pyo",
        ".pyd",
        ".wasm",
        ".node",
        ".elf",
        ".out",
        ".ko",
        ".ptx",
        # fonts
        ".ttf",
        ".otf",
        ".woff",
        ".woff2",
        ".eot",
        # office / PDF
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        ".odt",
        ".ods",
        ".odp",
        ".rtf",
        # databases & caches
        ".db",
        ".sqlite",
        ".sqlite3",
        ".mdb",
        ".pickle",
        ".pkl",
        ".npy",
        ".npz",
        ".h5",
        ".hdf5",
        ".parquet",
        ".feather",
        ".arrow",
        ".onnx",
        ".pb",
        ".tflite",
        ".ckpt",
        ".safetensors",
        # misc
        ".lockb",
        ".mp4a",
        ".dat",
        ".dmp",
        ".core",
        ".swp",
        ".swo",
    }
)

# --------------------------------------------------------------------------
# Secret detection — skipped by default, because the output is meant to be
# pasted into a third-party prompt.
# --------------------------------------------------------------------------

SECRET_NAMES = frozenset(
    {
        ".netrc",
        "_netrc",
        ".npmrc",
        ".pypirc",
        ".git-credentials",
        ".htpasswd",
        ".dockercfg",
        "credentials",
        "credentials.json",
        "secrets.json",
        "secrets.yaml",
        "secrets.yml",
        "secret.json",
        "keystore.jks",
        "secring.gpg",
        "service-account.json",
        "id_rsa",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
    }
)

SECRET_SUFFIXES = (
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".jks",
    ".keystore",
    ".ppk",
    ".asc",
    ".der",
    ".csr",
)

SECRET_PREFIXES = ("id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", ".env")

# Suffixes that mark a file as an obviously-safe *template* for secrets.
SAFE_SECRET_SUFFIXES = (".example", ".sample", ".template", ".dist", ".pub", ".md", ".rst", ".txt")


def language_for(name: str) -> str | None:
    """Return a Markdown fence language for *name*, or ``None`` if unknown."""
    lowered = name.lower()
    mapped = FILENAME_LANGUAGES.get(lowered)
    if mapped:
        return mapped
    ext = os.path.splitext(lowered)[1]
    return EXTENSION_LANGUAGES.get(ext)


def is_binary_extension(name: str) -> bool:
    """True when *name* has an extension that is never useful as prompt text."""
    ext = os.path.splitext(name.lower())[1]
    return ext in BINARY_EXTENSIONS


def is_secret_name(name: str) -> bool:
    """Heuristically decide whether *name* may hold credentials.

    The check is intentionally conservative: a false positive costs the user
    one ``--include-secrets`` flag, a false negative can leak a live key into
    somebody else's model context.
    """
    lowered = name.lower()
    if lowered.endswith(SAFE_SECRET_SUFFIXES):
        return False
    if lowered in SECRET_NAMES:
        return True
    if lowered.startswith(SECRET_PREFIXES):
        return True
    return bool(lowered.endswith(SECRET_SUFFIXES))


def any_secret(names: Iterable[str]) -> bool:
    """Convenience helper used by tests and callers that hold a name list."""
    return any(is_secret_name(name) for name in names)
