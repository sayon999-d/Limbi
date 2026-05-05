

from __future__ import annotations

import logging
import os
from typing import Any

from agents import BaseAgent

logger = logging.getLogger("limbi.agents.git")

class GitAgent(BaseAgent):
    agent_name = "git_agent"

    def __init__(self) -> None:
        self._token = os.getenv("GITHUB_TOKEN", "")
        self._owner = os.getenv("GITHUB_DEFAULT_OWNER", "")
        self._api = "https://api.github.com"

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "status": "ready",
            "github_configured": bool(self._token),
            "owner": self._owner or "(not set)",
        }

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def handle_create_branch(
        self,
        repo: str = "",
        branch: str = "",
        base: str = "main",
        **kwargs: Any,
    ) -> dict[str, Any]:

        logger.info("Creating branch '%s' from '%s' on %s/%s", branch, base, self._owner, repo)

        if self._token:
            import requests

            ref_url = f"{self._api}/repos/{self._owner}/{repo}/git/ref/heads/{base}"
            ref_resp = requests.get(ref_url, headers=self._headers(), timeout=10)
            if ref_resp.status_code != 200:
                raise RuntimeError(f"Failed to get base ref: {ref_resp.text}")
            sha = ref_resp.json()["object"]["sha"]

            create_url = f"{self._api}/repos/{self._owner}/{repo}/git/refs"
            create_resp = requests.post(
                create_url,
                headers=self._headers(),
                json={"ref": f"refs/heads/{branch}", "sha": sha},
                timeout=10,
            )
            if create_resp.status_code not in (200, 201):
                raise RuntimeError(f"Failed to create branch: {create_resp.text}")
            return {"message": f"Branch '{branch}' created from '{base}'", "sha": sha}

        return {
            "message": f"[SIMULATED] Branch '{branch}' created from '{base}' on {repo}",
            "repo": repo,
            "branch": branch,
            "base": base,
        }

    def handle_merge(
        self,
        repo: str = "",
        head: str = "",
        base: str = "main",
        commit_message: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:

        logger.info("Merging '%s' -> '%s' on %s/%s", head, base, self._owner, repo)

        if self._token:
            import requests

            url = f"{self._api}/repos/{self._owner}/{repo}/merges"
            resp = requests.post(
                url,
                headers=self._headers(),
                json={
                    "base": base,
                    "head": head,
                    "commit_message": commit_message or f"Merge {head} into {base}",
                },
                timeout=10,
            )
            if resp.status_code not in (200, 201):
                raise RuntimeError(f"Merge failed: {resp.text}")
            return {"message": f"Merged '{head}' into '{base}'", "sha": resp.json().get("sha")}

        return {
            "message": f"[SIMULATED] Merged '{head}' into '{base}' on {repo}",
            "repo": repo,
            "head": head,
            "base": base,
        }

    def handle_create_pr(
        self,
        repo: str = "",
        title: str = "",
        head: str = "",
        base: str = "main",
        body: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:

        logger.info("Creating PR '%s' (%s -> %s) on %s", title, head, base, repo)

        if self._token:
            import requests

            url = f"{self._api}/repos/{self._owner}/{repo}/pulls"
            resp = requests.post(
                url,
                headers=self._headers(),
                json={"title": title, "head": head, "base": base, "body": body},
                timeout=10,
            )
            if resp.status_code not in (200, 201):
                raise RuntimeError(f"PR creation failed: {resp.text}")
            pr_data = resp.json()
            return {
                "message": f"PR #{pr_data['number']} created",
                "pr_url": pr_data["html_url"],
                "number": pr_data["number"],
            }

        return {
            "message": f"[SIMULATED] PR '{title}' created ({head} -> {base}) on {repo}",
            "repo": repo,
            "title": title,
            "number": 42,
            "pr_url": f"https://github.com/{self._owner}/{repo}/pull/42",
        }

    def handle_list_repos(self, **kwargs: Any) -> dict[str, Any]:

        if self._token:
            import requests

            url = f"{self._api}/users/{self._owner}/repos?sort=updated&per_page=10"
            resp = requests.get(url, headers=self._headers(), timeout=10)
            if resp.status_code != 200:
                raise RuntimeError(f"Failed to list repos: {resp.text}")
            repos = [
                {"name": r["name"], "url": r["html_url"], "stars": r["stargazers_count"]}
                for r in resp.json()
            ]
            return {"repos": repos, "count": len(repos)}

        return {
            "message": "[SIMULATED] Repository listing",
            "repos": [
                {"name": "limbi", "url": "https://github.com/example/limbi"},
                {"name": "frontend", "url": "https://github.com/example/frontend"},
            ],
        }
