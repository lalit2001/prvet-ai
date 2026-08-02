from crv_adapters.forge.base import DiffHunk, ForgeAdapter, PullRequest, ReviewComment

__all__ = ["ForgeAdapter", "DiffHunk", "PullRequest", "ReviewComment"]


def get_adapter(forge_type: str) -> ForgeAdapter:
    """Late-import concrete adapter by name so unused ones stay unimported."""
    if forge_type == "github":
        from crv_adapters.forge.github import GitHubAdapter
        return GitHubAdapter()
    if forge_type == "gitlab":
        from crv_adapters.forge.gitlab import GitLabAdapter
        return GitLabAdapter()
    if forge_type == "azure_devops":
        from crv_adapters.forge.azdo import AzureDevOpsAdapter
        return AzureDevOpsAdapter()
    if forge_type == "bitbucket":
        from crv_adapters.forge.bitbucket import BitbucketAdapter
        return BitbucketAdapter()
    if forge_type == "gitea":
        from crv_adapters.forge.gitea import GiteaAdapter
        return GiteaAdapter()
    raise ValueError(f"unknown forge_type: {forge_type}")
