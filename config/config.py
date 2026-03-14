from pathlib import Path
import os
from pydantic import BaseModel, Field


class ModelConfig(BaseModel):
    name: str = "nvidia/nemotron-3-nano-30b-a3b:free"
    # temperature controls the creativity of the model
    temperature: float = Field(default=1, ge=0.0, le=2.0)
    context_window: int = 256_000  # number of tokens a model can handle


class Config (BaseModel):
    model: ModelConfig = Field(default_factory=ModelConfig)
    cwd: Path = Field(default_factory=Path.cwd)

    max_turns: int = 100
    max_tool_output_tokens: int = 50_000

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
