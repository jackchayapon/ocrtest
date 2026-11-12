from uuid import uuid4

from sqlalchemy import func, select

from app.core.errors import AppError
from app.db.models import ExternalProvider, PipelineConfig, now
from app.integrations.external_ocr import Provider, validate_url
from app.services.provider_credentials import (
    decrypt_credential,
    encrypt_credential,
    endpoint_origin,
    same_credential,
)


def provider_from_record(record, settings):
    provider = Provider.model_validate(record.config)
    provider._managed = True
    provider._enabled = record.enabled
    provider._credential_configured = bool(record.encrypted_credential)
    ciphertext = record.encrypted_credential
    if ciphertext:
        provider._credential_loader = lambda: decrypt_credential(settings, ciphertext, record.id, record.config["endpoint"])
    return provider


def validate_provider(provider, settings):
    origin = validate_url(provider.endpoint, settings.external_ocr_development)
    if provider.readiness_url:
        ready = validate_url(provider.readiness_url, settings.external_ocr_development)
        if (origin.scheme, origin.hostname, origin.port) != (ready.scheme, ready.hostname, ready.port):
            raise ValueError("Readiness must share the inference origin")


class ExternalProviderService:
    def __init__(self, session, settings):
        self.session, self.settings = session, settings

    def record(self, provider_id):
        record = self.session.get(ExternalProvider, provider_id)
        if record is None:
            raise AppError("Managed external provider not found", 404)
        return record

    def serialize(self, record):
        return {**provider_from_record(record, self.settings).public(record.id),
                "revision": record.revision, "created_at": record.created_at.isoformat(),
                "updated_at": record.updated_at.isoformat()}

    def save(self, data, provider_id=None, commit=True):
        try:
            validate_provider(data, self.settings)
        except ValueError:
            raise AppError("Use a public HTTPS endpoint and same-origin readiness URL", 422) from None
        if provider_id:
            record = self.record(provider_id)
        else:
            if self.session.scalar(select(func.count()).select_from(ExternalProvider)) >= 50:
                raise AppError("Managed provider capacity reached", 409)
            record = ExternalProvider(id="managed_" + uuid4().hex, revision=0)
        ciphertext = record.encrypted_credential
        old_endpoint = (record.config or {}).get("endpoint")
        changed_origin = old_endpoint is not None and endpoint_origin(old_endpoint) != endpoint_origin(data.endpoint)
        if changed_origin and ciphertext and data.auth_mode != "none":
            if data.credential_action == "keep":
                raise AppError("Endpoint origin changed. Enter a new API key or disable authentication.", 422)
            if data.credential_action == "replace" and same_credential(data.api_key.get_secret_value(),
                    decrypt_credential(self.settings, ciphertext, record.id, old_endpoint)):
                raise AppError("Use a new credential for the changed endpoint origin.", 422)
        if data.auth_mode == "none" or data.credential_action == "remove":
            ciphertext = None
        elif data.credential_action == "replace":
            ciphertext = encrypt_credential(self.settings, data.api_key.get_secret_value(), record.id, data.endpoint)
        elif changed_origin:
            ciphertext = None
        if data.auth_mode != "none" and not ciphertext and data.enabled:
            raise AppError("Configure a credential or disable this provider", 422)
        if ciphertext:
            secret = decrypt_credential(self.settings, ciphertext, record.id, data.endpoint)
            if any(secret in value for value in data.provider_config().values() if isinstance(value, str)):
                raise AppError("Do not include credentials in public provider configuration fields", 422)
        record.config = data.provider_config()
        record.encrypted_credential = ciphertext
        record.enabled = data.enabled
        record.revision += 1
        record.updated_at = now()
        self.session.add(record)
        self.session.flush()
        provider = provider_from_record(record, self.settings)
        # Future Jobs use the new definition. Already accepted Job snapshots are
        # immutable and fail closed if their public routing fingerprint changed.
        for config in self.session.scalars(select(PipelineConfig).where(
                PipelineConfig.execution_mode == "external_api",
                PipelineConfig.integrated_options["provider_id"].as_string() == record.id)):
            config.integrated_options = provider.identity(record.id)
            config.last_connection_status = None
        if commit:
            self.session.commit()
        return record

    def delete(self, provider_id):
        record = self.record(provider_id)
        count = self.session.scalar(select(func.count()).select_from(PipelineConfig).where(
            PipelineConfig.execution_mode == "external_api",
            PipelineConfig.integrated_options["provider_id"].as_string() == provider_id))
        if count:
            raise AppError("Remove or reconfigure pipelines using this provider before deleting it", 409)
        self.session.delete(record)
        self.session.commit()
