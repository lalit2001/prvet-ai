"""Azure DevOps adapter — full impl lands in M4."""
from crv_adapters.forge.base import ForgeEvent


class AzureDevOpsAdapter:
    forge_type = "azure_devops"

    async def verify_webhook(self, headers, body, secret):
        raise NotImplementedError  # M4 — ADO uses HTTP basic on the webhook itself

    def parse_event(self, headers, payload) -> ForgeEvent | None:
        raise NotImplementedError

    async def get_pull_request(self, repo, number): raise NotImplementedError
    async def get_diff(self, repo, base_sha, head_sha): raise NotImplementedError
    async def get_file_content(self, repo, path, ref): raise NotImplementedError
    async def post_review(self, repo, pr, commit_sha, summary, comments): raise NotImplementedError
    async def update_comment(self, repo, comment_id, body): raise NotImplementedError
    async def resolve_thread(self, repo, comment_id): raise NotImplementedError
    async def set_status(self, repo, commit_sha, state, title, summary, details_url): raise NotImplementedError
    async def get_user_permission(self, repo, external_user_id): raise NotImplementedError
    async def supports(self, capability: str) -> bool: return False
    async def get_clone_credentials(self, repo): raise NotImplementedError
