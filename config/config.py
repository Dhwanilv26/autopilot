from __future__ import annotations
from enum import Enum
from pathlib import Path
import os
from typing import Any
from pydantic import BaseModel, Field, model_validator


class ModelConfig(BaseModel):
    name: str = "openrouter/free"
    # temperature controls the creativity of the model
    temperature: float = Field(default=1, ge=0.0, le=2.0)
    context_window: int = 256_000  # number of tokens a model can handle


class ShellEnvironmentPolicy(BaseModel):
    # ignoring std patterns like ["KEY","TOKEN","SECRET"] to avoid passing of API_KEYS to the LLM (false means dont ignore default excludes)
    ignore_default_excludes: bool = False
    exclude_patterns: list[str] = Field(default_factory=lambda: ["*KEY*", "*TOKEN*", "*SECRET*"])
    # NODE_ENV -> production to dev change
    set_vars: dict[str, str] = Field(default_factory=dict)


class MCPServerConfig(BaseModel):
    enabled: bool = True
    startup_timeout_sec: float = 10

    # stdio transport (for local mcp (command and args are required))
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    cwd: Path | None = None

    # HTTP/SSE transport
    url: str | None = None

    @model_validator(mode='after')  # runs after object creation
    def validate_transport(self) -> MCPServerConfig:
        has_command = self.command is not None
        has_url = self.url is not None

        if not has_command and not has_url:
            raise ValueError("mcp server must have either 'command' (stdio) or 'url' (http/sse)")

        if has_command and has_url:
            raise ValueError("mcp server can not have both 'command' (stdio) and 'url' (http/sse)")

        return self


class ApprovalPolicy(str, Enum):
    ON_REQUEST = "on-request"  # ask when agent explicitly asks for permission
    ON_FAILURE = "on-failure"  # ask to user on failure, till then let the codef
    AUTO = "auto"  # auto approve all SAFE_COMMANDS and reject others
    AUTO_EDIT = "auto-edit"  # auto approve all edit commands
    NEVER = "never"  # never ask for any approval, but still follow safety rules
    YOLO = "yolo"  # auto approves everything , even dangerous commands


class HookTrigger(str, Enum):
    BEFORE_AGENT = "before_agent"
    AFTER_AGENT = "after_agent"
    BEFORE_TOOL = "before_tool"
    AFTER_TOOL = "after_tool"
    ON_ERROR = "on_error"


class HookConfig(BaseModel):
    name: str
    trigger: HookTrigger
    command: str | None = None  # simple python commands or code commands
    script: str | None = None  # all scripts possible in .sh form
    timeout_sec: float = 30
    enabled: bool = True

    @model_validator(mode="after")
    def validate_hook(self) -> HookConfig:

        if not (self.command or self.script):
            raise ValueError("Provide either command or script")

        if self.command and self.script:
            raise ValueError("Provide only one of command or script")

        return self


class Config (BaseModel):
    model: ModelConfig = Field(default_factory=ModelConfig)
    cwd: Path = Field(default_factory=Path.cwd)

    shell_environment: ShellEnvironmentPolicy = Field(default_factory=ShellEnvironmentPolicy)

    hooks_enabled: bool = False
    hooks: list[HookConfig] = Field(default_factory=list)

    approval: ApprovalPolicy = ApprovalPolicy.ON_REQUEST

    max_turns: int = 100
    max_tool_output_tokens: int = 50_000

    # mcp server name and the whole class to describe it
    # mcp_servers is a dict and not a list because lookup operations in dict are O(1) and not O(N), no duplicate keys and easier validaton for pydantic (sab dict mai hi parse hoke aayega)
    mcp_servers: dict[str, MCPServerConfig] = Field(default_factory=dict)
    allowed_tools: list[str] | None = Field(
        None, description="If this value is set, only these tools will be available to the agent.")

    # written in agents.md file
    developer_instructions: str | None = None
    user_instructions: str | None = None

    debug: bool = False  # to display the logger stuff using --debug

    @property
    def api_key(self) -> str | None:
        return os.environ.get("API_KEY")

    @property
    def base_url(self) -> str | None:
        return os.environ.get("BASE_URL")

    @property
    def model_name(self) -> str | None:
        return self.model.name

    # @property_name.setter
    @model_name.setter
    def model_name(self, value: str):
        self.model.name = value

    @property
    def temperature(self) -> float:
        return self.model.temperature

    @temperature.setter
    def temperature(self, value: float) -> None:
        self.model.temperature = value

    def get_validation_errors(self) -> list[str]:
        errors: list[str] = []
        if not self.api_key:
            errors.append("NO API_KEY FOUND. Set API_KEY ENV Variable")

        if not self.cwd.exists():
            errors.append(f"working directory does not exist: {self.cwd}")

        return errors

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
