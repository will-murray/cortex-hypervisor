"""
Google Cloud Secret Manager client for cortex-hypervisor.

All secrets are fetched once at import time and cached — Secret Manager is
billed per access and adds ~50ms RTT per call.

Requires:
  - GCP_PROJECT env var (the only non-secret config needed to bootstrap)
  - Application Default Credentials (ADC):
      Locally:    `gcloud auth application-default login`
      Production: compute service identity (Cloud Run, GCE, etc.)
"""
from functools import lru_cache
import os

from google.cloud import secretmanager

_client = secretmanager.SecretManagerServiceClient()
_project = os.environ["GCP_PROJECT"]


@lru_cache(maxsize=None)
def get_secret(name: str, version: str = "latest") -> str:
    """Fetch a secret from Google Cloud Secret Manager (cached)."""
    path = f"projects/{_project}/secrets/{name}/versions/{version}"
    return _client.access_secret_version(
        request={"name": path}
    ).payload.data.decode("utf-8")
