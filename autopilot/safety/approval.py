from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import re
from typing import Any, Awaitable, Callable

from autopilot.config.config import ApprovalPolicy
from autopilot.tools.base import ToolConfirmation


class ApprovalDecision(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_CONFIRMATION = "needs_confirmation"


@dataclass
class ApprovalContext:
    tool_name: str
    params: dict[str, Any]
    is_mutating: bool
    affected_paths: list[Path]
    # for simplified auto approve mode (user ko nai puchna padega baar baar)
    command: str | None = None  # for shell commands
    is_dangerous: bool = False


DANGEROUS_PATTERNS = [
    # File system destruction
    r"rm\s+(-rf?|--recursive)\s+[/~]",
    r"rm\s+-rf?\s+\*",
    r"rmdir\s+[/~]",
    # Disk operations
    r"dd\s+if=",
    r"mkfs",
    r"fdisk",
    r"parted",
    # System control
    r"shutdown",
    r"reboot",
    r"halt",
    r"poweroff",
    r"init\s+[06]",
    # Permission changes on root
    r"chmod\s+(-R\s+)?777\s+[/~]",
    r"chown\s+-R\s+.*\s+[/~]",
    # Network exposure
    r"nc\s+-l",
    r"netcat\s+-l",
    # Code execution from network
    r"curl\s+.*\|\s*(bash|sh)",
    r"wget\s+.*\|\s*(bash|sh)",
    # Fork bomb
    r":\(\)\s*\{\s*:\|:&\s*\}\s*;",
]

# Patterns for safe commands (can be auto-approved)
SAFE_PATTERNS = [
    # Information commands
    r"^(ls|dir|pwd|cd|echo|cat|head|tail|less|more|wc)(\s|$)",
    r"^(find|locate|which|whereis|file|stat)(\s|$)",
    # Development tools (read-only)
    r"^git\s+(status|log|diff|show|branch|remote|tag)(\s|$)",
    r"^(npm|yarn|pnpm)\s+(list|ls|outdated)(\s|$)",
    r"^pip\s+(list|show|freeze)(\s|$)",
    r"^cargo\s+(tree|search)(\s|$)",
    # Text processing (usually safe)
    r"^(grep|awk|sed|cut|sort|uniq|tr|diff|comm)(\s|$)",
    # System info
    r"^(date|cal|uptime|whoami|id|groups|hostname|uname)(\s|$)",
    r"^(env|printenv|set)$",
    # Process info
    r"^(ps|top|htop|pgrep)(\s|$)",
]


def is_dangerous_command(command: str) -> bool:
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return True

    return False


def is_safe_command(command: str) -> bool:
    for pattern in SAFE_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return True

    return False


class ApprovalManager:
    def __init__(self, approval_policy: ApprovalPolicy,
                 cwd: Path,
                 # toolconfirmation is input, and bool is output returned (for callable (type check only)), confirmation_callback can be none as YOLO NEVER AUTO never require userinput
                 confirmation_callback:
                 Callable[[ToolConfirmation], Awaitable[bool]] | None = None) -> None:
        self.approval_policy = approval_policy
        self.cwd = cwd
        self.confirmation_callback = confirmation_callback

    def _assess_command_safety(self, command: str) -> ApprovalDecision:
        if self.approval_policy == ApprovalPolicy.YOLO:
            return ApprovalDecision.APPROVED

        if is_dangerous_command(command):
            return ApprovalDecision.REJECTED

        if self.approval_policy == ApprovalPolicy.NEVER:
            # never means no user interaction, system has to decide alone, only safe command allowed
            if is_safe_command(command):
                return ApprovalDecision.APPROVED
            return ApprovalDecision.REJECTED

        # rest all policies need user interaction so
        if self.approval_policy == ApprovalPolicy.AUTO:
            if is_safe_command(command):
                return ApprovalDecision.APPROVED
            return ApprovalDecision.NEEDS_CONFIRMATION

        if self.approval_policy == ApprovalPolicy.ON_FAILURE:
            return ApprovalDecision.APPROVED  # failure hoga tab dekhlenege, abhi ke liye approved hai

        if self.approval_policy == ApprovalPolicy.AUTO_EDIT:
            if is_safe_command(command):
                return ApprovalDecision.APPROVED
            return ApprovalDecision.NEEDS_CONFIRMATION

        if is_safe_command(command):
            return ApprovalDecision.APPROVED

        return ApprovalDecision.NEEDS_CONFIRMATION

    async def check_approval(self, context: ApprovalContext) -> ApprovalDecision:
        # not good if we are giving the llm to read .env files
        if not context.is_mutating:
            return ApprovalDecision.APPROVED

        if context.command:
            decision = self._assess_command_safety(context.command)
            if decision != ApprovalDecision.NEEDS_CONFIRMATION:
                # approved ya rejected (hum sure hai iske liye), needs_approval ke liye later checks aayenge
                return decision

        for path in context.affected_paths:
            path_decision = ApprovalDecision.NEEDS_CONFIRMATION
            if path.is_relative_to(self.cwd):
                path_decision = ApprovalDecision.APPROVED
            else:
                return path_decision

        if context.is_dangerous:
            if self.approval_policy == ApprovalPolicy.YOLO:
                return ApprovalDecision.APPROVED
            return ApprovalDecision.NEEDS_CONFIRMATION

        return ApprovalDecision.NEEDS_CONFIRMATION

    async def request_confirmation(self, confirmation: ToolConfirmation) -> bool:
        if self.confirmation_callback:
            result = await self.confirmation_callback(confirmation)
            return result

        return True
