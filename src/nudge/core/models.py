"""Data models for Nudge hint store."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union
from enum import Enum


# Enums
class OS(str, Enum):
    """Operating system types."""
    LINUX = "linux"
    DARWIN = "darwin"
    WINDOWS = "windows"


class ShellType(str, Enum):
    """Shell types for command execution."""
    BASH = "bash"
    SH = "sh"
    POWERSHELL = "powershell"
    CMD = "cmd"


class TemplateFormat(str, Enum):
    """Template formats."""
    MUSTACHE = "mustache"
    HANDLEBARS = "handlebars"
    JINJA = "jinja"
    INTERPOLATE = "interpolate"


class Sensitivity(str, Enum):
    """Hint sensitivity level."""
    SECRET = "secret"
    NORMAL = "normal"


class HintSource(str, Enum):
    """Source of the hint."""
    USER = "user"
    AGENT = "agent"
    TOOL_OUTPUT = "tool-output"
    FILE_IMPORT = "file-import"


# HintValue types
@dataclass
class CommandValue:
    """Command hint value."""
    type: Literal["command"] = "command"
    cmd: str = ""
    shell: Optional[ShellType] = None


@dataclass
class PathValue:
    """Path hint value."""
    type: Literal["path"] = "path"
    abs: str = ""
    os: Optional[List[OS]] = None


@dataclass
class TemplateValue:
    """Template hint value."""
    type: Literal["template"] = "template"
    format: TemplateFormat = TemplateFormat.INTERPOLATE
    body: str = ""
    defaults: Optional[Dict[str, str]] = None


@dataclass
class JsonValue:
    """JSON hint value."""
    type: Literal["json"] = "json"
    data: Any = None


# Union type for all hint values
HintValue = Union[str, CommandValue, PathValue, TemplateValue, JsonValue]


@dataclass
class Scope:
    """Scope conditions for hint eligibility."""
    cwd_glob: Optional[List[str]] = None
    repo: Optional[Union[str, List[str]]] = None
    branch: Optional[List[str]] = None
    os: Optional[List[OS]] = None
    env_required: Optional[List[str]] = None
    env_match: Optional[Dict[str, Union[str, List[str]]]] = None


@dataclass
class HintMeta:
    """Metadata for a hint."""
    reason: Optional[str] = None
    tags: Optional[List[str]] = None
    priority: Optional[int] = None  # 1-10
    confidence: Optional[float] = None  # 0.0-1.0
    ttl: Optional[str] = None  # "session" or ISO-8601 duration
    sensitivity: Optional[Sensitivity] = None
    scope: Optional[Scope] = None
    source: Optional[HintSource] = None
    added_by: Optional[str] = None


@dataclass
class Hint:
    """A hint with value, metadata, and version tracking."""
    value: HintValue
    meta: HintMeta = field(default_factory=HintMeta)
    version: int = 1
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    last_used_at: Optional[str] = None
    use_count: int = 0


@dataclass
class ComponentHints:
    """Hints for a component."""
    hints: Dict[str, Hint] = field(default_factory=dict)


@dataclass
class NudgeStore:
    """The main hint store."""
    schema_version: str = "1.0"
    session_id: str = ""
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    components: Dict[str, ComponentHints] = field(default_factory=dict)


@dataclass
class NudgeContext:
    """Runtime context for matching hints."""
    cwd: Optional[str] = None
    repo: Optional[str] = None
    branch: Optional[str] = None
    os: Optional[OS] = None
    env: Optional[Dict[str, Optional[str]]] = None
    files_open: Optional[List[str]] = None


@dataclass
class MatchExplanation:
    """Explanation of why a hint matched."""
    matched: bool
    score: float
    reasons: List[str] = field(default_factory=list)


@dataclass
class HintMatch:
    """A hint with its match score and explanation."""
    hint: Hint
    score: float
    match_explain: MatchExplanation


# Error codes
class ErrorCode(Enum):
    """Nudge error codes."""
    E_NOT_FOUND = 40401
    E_INVALID = 40001
    E_CONFLICT = 40901
    E_SECRET_REJECTED = 40002
    E_SCOPE_INVALID = 40003
    E_QUOTA = 42901
