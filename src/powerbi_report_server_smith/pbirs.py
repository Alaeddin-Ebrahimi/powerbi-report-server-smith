"""
Power BI Report Server (on-prem) deployment layer.

*** STATUS: written to the documented REST API v2.0 spec, NOT verified
against a live Power BI Report Server — there was no test instance available
when this was built. Treat this layer as a solid starting point, not a
finished, battle-tested integration. Test it against a real (ideally
non-production) PBIRS instance before pointing it at anything that matters,
and expect to adjust auth/endpoint details if your server's configuration
differs (e.g. Kerberos instead of NTLM, a custom virtual directory instead
of the default /Reports path). ***

Auth: PBIRS typically uses Windows Integrated Auth (NTLM or Kerberos), not
OAuth/Entra ID — this is the actual reason none of the general-purpose Power
BI MCP servers cover it; they all assume cloud auth.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

try:
    import requests
    from requests_ntlm2 import HttpNtlmAuth  # pip install requests_ntlm2
    _HAS_NTLM = True
except ImportError:
    _HAS_NTLM = False


@dataclass
class PbirsConfig:
    base_url: str          # e.g. "https://intranet-host/Reports"
    username: str | None = None
    password: str | None = None
    verify_ssl: bool = True

    @classmethod
    def from_env(cls) -> "PbirsConfig":
        """
        Reads connection details from environment variables — never from
        hardcoded values in this file. Set these in your MCP client's env
        config or a local .env you load yourself; do not commit them.

          PBIRS_BASE_URL   e.g. https://intranet-host/Reports
          PBIRS_USERNAME    DOMAIN\\user  (optional — omit to use the
                             current process's Windows credentials, if
                             running on a domain-joined Windows host)
          PBIRS_PASSWORD
          PBIRS_VERIFY_SSL  "true" / "false" (default true)
        """
        base_url = os.environ.get("PBIRS_BASE_URL", "")
        if not base_url:
            raise ValueError("PBIRS_BASE_URL environment variable is not set")
        return cls(
            base_url=base_url.rstrip("/"),
            username=os.environ.get("PBIRS_USERNAME") or None,
            password=os.environ.get("PBIRS_PASSWORD") or None,
            verify_ssl=os.environ.get("PBIRS_VERIFY_SSL", "true").lower() != "false",
        )


class PbirsClient:
    """Thin wrapper over the PBIRS REST API v2.0 (/Reports/api/v2.0/...)."""

    def __init__(self, config: PbirsConfig | None = None):
        if not _HAS_NTLM:
            raise ImportError(
                "requests_ntlm2 is not installed. Run: pip install requests_ntlm2"
            )
        self.config = config or PbirsConfig.from_env()
        self._session = requests.Session()
        if self.config.username and self.config.password:
            self._session.auth = HttpNtlmAuth(self.config.username, self.config.password)
        self._api_root = f"{self.config.base_url}/api/v2.0"

    def _get(self, path: str, params: dict | None = None) -> dict:
        resp = self._session.get(f"{self._api_root}{path}", params=params, verify=self.config.verify_ssl)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, json_body: dict | None = None, data: bytes | None = None,
              headers: dict | None = None) -> dict:
        resp = self._session.post(
            f"{self._api_root}{path}", json=json_body, data=data,
            headers=headers, verify=self.config.verify_ssl,
        )
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    # --- Catalog / folders -------------------------------------------------

    def list_folders(self, parent_path: str = "/") -> list[dict]:
        result = self._get("/Folders", params={"$filter": f"Path eq '{parent_path}'"})
        return result.get("value", [])

    def create_folder(self, parent_path: str, name: str) -> dict:
        return self._post("/Folders", json_body={"Name": name, "Parent": parent_path})

    def list_catalog_items(self, folder_path: str) -> list[dict]:
        result = self._get("/CatalogItems", params={"$filter": f"Path eq '{folder_path}'"})
        return result.get("value", [])

    # --- Reports -------------------------------------------------------------

    def upload_report(self, folder_path: str, name: str, pbix_bytes: bytes) -> dict:
        """
        Uploads a .pbix as a new PowerBIReport catalog item. Per PBIRS REST
        API v2.0 convention this is a two-step create-then-upload-content
        operation in some server versions — confirm against your server's
        actual behavior once you have a test instance; this is the
        documented happy path, not verified live.
        """
        create_body = {
            "Name": name,
            "Path": f"{folder_path.rstrip('/')}/{name}",
        }
        created = self._post("/PowerBIReports", json_body=create_body)
        item_id = created.get("Id")
        if item_id:
            self._post(
                f"/PowerBIReports({item_id})/Content.UpdateContent",
                data=pbix_bytes,
                headers={"Content-Type": "application/octet-stream"},
            )
        return created

    def download_report_definition(self, item_id: str) -> bytes:
        resp = self._session.get(
            f"{self._api_root}/PowerBIReports({item_id})/Content.Value",
            verify=self.config.verify_ssl,
        )
        resp.raise_for_status()
        return resp.content

    # --- Permissions / subscriptions / refresh -------------------------------

    def set_permissions(self, item_id: str, policies: list[dict]) -> dict:
        return self._post(f"/CatalogItems({item_id})/Policies", json_body={"value": policies})

    def list_subscriptions(self, item_id: str) -> list[dict]:
        result = self._get(f"/CatalogItems({item_id})/Subscriptions")
        return result.get("value", [])

    def create_subscription(self, item_id: str, subscription: dict) -> dict:
        return self._post(f"/CatalogItems({item_id})/Subscriptions", json_body=subscription)

    def trigger_refresh_plan(self, refresh_plan_id: str) -> dict:
        return self._post(f"/RefreshPlans({refresh_plan_id})/Model.ExecuteRefreshPlan")


# --- MCP tool-facing wrapper functions --------------------------------------
# Each of these builds its own client from environment config per call, so no
# credential lives in memory longer than one tool invocation.

def pbirs_list_folders(parent_path: str = "/") -> dict:
    client = PbirsClient()
    return {"folders": client.list_folders(parent_path)}


def pbirs_create_folder(parent_path: str, name: str) -> dict:
    client = PbirsClient()
    return client.create_folder(parent_path, name)


def pbirs_list_catalog_items(folder_path: str) -> dict:
    client = PbirsClient()
    return {"items": client.list_catalog_items(folder_path)}


def pbirs_upload_report(folder_path: str, name: str, pbix_file_path: str) -> dict:
    with open(pbix_file_path, "rb") as f:
        pbix_bytes = f.read()
    client = PbirsClient()
    return client.upload_report(folder_path, name, pbix_bytes)


def pbirs_list_subscriptions(item_id: str) -> dict:
    client = PbirsClient()
    return {"subscriptions": client.list_subscriptions(item_id)}


def pbirs_trigger_refresh_plan(refresh_plan_id: str) -> dict:
    client = PbirsClient()
    return client.trigger_refresh_plan(refresh_plan_id)
