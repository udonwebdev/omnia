"""
OMNIA Module 44: Autonomous Software Delivery, CI/CD Intelligence & Release Engineering
Source Control Intelligence - source_analyzer.py

Analyzes repository metadata, revisions, branches, commits, and categorizes file modifications.
"""

from __future__ import annotations

import logging
import os
import subprocess
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from software_delivery.models import (
    ChangeCategory,
    RepositoryType,
    SourceRepository,
    SourceRevision,
)
from software_delivery.persistence import SoftwareDeliveryRepository

logger = logging.getLogger("Omnia.SoftwareDelivery.SourceAnalyzer")


class SourceAnalyzer:
    """
    Inspects repository metadata, commit histories, and file changes.
    Supports local git workspaces and simulated VCS providers.
    """

    def __init__(self, repository: Optional[SoftwareDeliveryRepository] = None):
        self.repo = repository or SoftwareDeliveryRepository()

    def register_repository(
        self,
        name: str,
        clone_url: str,
        provider_type: RepositoryType = RepositoryType.GIT_LOCAL,
        default_branch: str = "main",
        repository_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SourceRepository:
        rid = repository_id or f"repo-{uuid.uuid4().hex[:8]}"
        r = SourceRepository(
            repository_id=rid,
            name=name,
            provider_type=provider_type,
            clone_url=clone_url,
            default_branch=default_branch,
            metadata=metadata or {},
        )
        self.repo.save_repository(r)
        logger.info(f"Registered repository: {rid} ({name}) at {clone_url}")
        return r

    def record_revision(
        self,
        repository_id: str,
        commit_hash: str,
        branch: str,
        author: str,
        commit_message: str,
        parent_commits: Optional[List[str]] = None,
        revision_id: Optional[str] = None,
    ) -> SourceRevision:
        rev_id = revision_id or f"rev-{uuid.uuid4().hex[:8]}"
        rev = SourceRevision(
            revision_id=rev_id,
            repository_id=repository_id,
            commit_hash=commit_hash,
            branch=branch,
            author=author,
            commit_message=commit_message,
            parent_commits=parent_commits or [],
        )
        self.repo.save_revision(rev)
        logger.info(f"Recorded source revision: {rev_id} ({commit_hash[:7]} on {branch})")
        return rev

    def detect_current_revision(
        self,
        repository_id: str,
        repo_dir: str = ".",
    ) -> SourceRevision:
        """Inspects live git repository on disk to capture HEAD commit."""
        try:
            commit_hash = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=repo_dir, text=True
            ).strip()
            branch = subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_dir, text=True
            ).strip()
            author = subprocess.check_output(
                ["git", "log", "-1", "--format=%an <%ae>"], cwd=repo_dir, text=True
            ).strip()
            msg = subprocess.check_output(
                ["git", "log", "-1", "--format=%s"], cwd=repo_dir, text=True
            ).strip()
        except Exception as e:
            logger.warning(f"Failed to query git CLI in {repo_dir}: {e}. Falling back to default.")
            commit_hash = "head00000000"
            branch = "main"
            author = "Omnia Autonomous Agent"
            msg = "Autonomous commit"

        return self.record_revision(
            repository_id=repository_id,
            commit_hash=commit_hash,
            branch=branch,
            author=author,
            commit_message=msg,
        )

    def categorize_file(self, filepath: str) -> ChangeCategory:
        """Determines the semantic change category of a file path."""
        p = filepath.replace("\\", "/").lower()
        if "migration" in p or "alembic" in p or "flyway" in p or p.endswith(".sql"):
            return ChangeCategory.DATABASE_MIGRATION
        if p.endswith("requirements.txt") or p.endswith("pyproject.toml") or p.endswith("package.json") or "lock" in p:
            return ChangeCategory.DEPENDENCY
        if "test" in p or p.startswith("tests/") or p.endswith("_test.py"):
            return ChangeCategory.TEST
        if p.endswith(".md") or p.endswith(".rst") or "/docs/" in p:
            return ChangeCategory.DOCUMENTATION
        if "secret" in p or "auth" in p or "security" in p or "cipher" in p or "ssl" in p:
            return ChangeCategory.SECURITY_CRITICAL
        if p.endswith(".yaml") or p.endswith(".yml") or p.endswith(".json") or p.endswith(".ini") or p.endswith(".env"):
            return ChangeCategory.CONFIGURATION
        return ChangeCategory.CODE
