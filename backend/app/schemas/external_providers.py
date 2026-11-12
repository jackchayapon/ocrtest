from typing import Literal

from pydantic import Field, SecretStr, model_validator

from app.integrations.external_ocr import Provider
from app.schemas.contracts import InputModel


class ProviderWrite(Provider):
    enabled: bool = True
    credential_env: None = None
    credential_action: Literal["keep", "replace", "remove"] = "keep"
    api_key: SecretStr | None = Field(default=None, min_length=1, max_length=4096)

    @model_validator(mode="after")
    def key_action(self):
        if (self.credential_action == "replace") != (self.api_key is not None):
            raise ValueError("Supply an API key only when replacing a credential")
        if self.auth_mode == "none" and self.api_key is not None:
            raise ValueError("Enable API key authentication before supplying a credential")
        if self.api_key is not None and any(ord(char) < 33 or ord(char) > 126 for char in self.api_key.get_secret_value()):
            raise ValueError("API keys must contain printable header characters without whitespace")
        return self

    def provider_config(self):
        return self.model_dump(exclude={"enabled", "credential_action", "api_key", "credential_env"})


class ExternalPipelineWrite(InputModel):
    pipeline_id: str | None = Field(default=None, pattern=r"^dynamic_[a-f0-9]{32}$")
    provider_id: str | None = Field(default=None, pattern=r"^managed_[a-f0-9]{32}$")
    pipeline_name: str = Field(min_length=1, max_length=100)
    pipeline_enabled: bool = True
    provider: ProviderWrite
