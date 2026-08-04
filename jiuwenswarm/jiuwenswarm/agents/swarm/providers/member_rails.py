# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Swarm member rail providers (config-sourced, per-member).

Each provider is a factory ``factory(params, context) -> rail | list | None``
invoked by openjiuwen at build time with the per-member ``SwarmBuildContext``.
Returning ``None`` / ``[]`` means "skip this rail for this member" (config gate).
Providers take precedence over same-named class registrations.

Mirrors the legacy ``build_member_rails`` runtime-prompt / report-path /
context-processor segments and the team manager plugin-rails segment, but driven
by the build context instead of imperatively threaded dataclasses.
"""

from __future__ import annotations

import inspect
import logging
import re
from functools import wraps
from importlib.metadata import version as distribution_version
from pathlib import Path
from typing import Any

from openjiuwen.agent_teams.harness.manifest import (
    ConstructionInput,
    context_field,
    ElementKind,
    harness_element,
    param_field,
)
from openjiuwen.agent_teams.rails.builtin_elements import (
    HEARTBEAT as CORE_HEARTBEAT,
    OBSERVABILITY as CORE_OBSERVABILITY,
    SECURITY as CORE_SECURITY,
)
from openjiuwen.agent_teams.rails.elements import TEAM_POLICY, TEAM_TOOL
from openjiuwen.agent_teams.rails.team_context import (
    get_messager,
    get_on_teammate_created,
    get_permissions_override,
    get_team_backend,
)
from openjiuwen.agent_teams.schema.deep_agent_spec import (
    DeepAgentSpec,
    register_rail_provider,
)
from openjiuwen.core.single_agent.prompts.builder import PromptSection
from openjiuwen.core.single_agent.rail.base import AgentCallbackContext
from openjiuwen.core.sys_operation import LocalWorkConfig, OperationMode
from openjiuwen.core.sys_operation.sys_operation import SysOperation, SysOperationCard
from openjiuwen.harness.rails.base import DeepAgentRail

from jiuwenswarm.agents.harness.common.plugins.rail_manager import get_rail_manager
from jiuwenswarm.agents.harness.common.rails.runtime_prompt_rail import (
    RuntimePromptRail,
)
from jiuwenswarm.agents.harness.common.rails.skill_retrieval_prompt_rail import (
    SkillRetrievalPromptRail,
)
from jiuwenswarm.agents.harness.common.rails.symphony_orchestration_prompt_rail import (
    SymphonyOrchestrationPromptRail,
)
from jiuwenswarm.agents.harness.team.rails.team_skill_storage_policy_rail import (
    TeamSkillStoragePolicyRail,
)
from jiuwenswarm.agents.harness.team.rails.team_shared_skill_link_refresh_rail import (
    TeamSharedSkillLinkRefreshRail,
)
from jiuwenswarm.agents.harness.team.rails.team_workspace_report_path_rail import (
    TeamWorkspaceReportPathRail,
)
from jiuwenswarm.agents.harness.team.team_runtime_inheritance import (
    _build_context_processor_rail,
)
from jiuwenswarm.agents.swarm.context import SwarmBuildContext

logger = logging.getLogger(__name__)

RUNTIME_PROMPT = "swarm.runtime_prompt"
TEAM_SKILL_STORAGE_POLICY = "swarm.team_skill_storage_policy"
TEAM_SHARED_SKILL_LINK_REFRESH = "swarm.team_shared_skill_link_refresh"
TEAM_WORKSPACE_REPORT_PATH = "swarm.team_workspace_report_path"
CONTEXT_PROCESSOR = "swarm.context_processor"
PLUGIN_RAILS = "swarm.plugin_rails"
SKILL_RETRIEVAL_PROMPT = "swarm.skill_retrieval_prompt"
SYMPHONY_ORCHESTRATION_PROMPT = "swarm.symphony_orchestration_prompt"
TEAM_PERMISSION_POLICY = "swarm.team_permission_policy"

_FIXED_QUANT_PROFILE_KEY = "_fixed_quant_pipeline"
_SUPPORTED_OPENJIUWEN_VERSION = "0.1.15.post3"
_FIXED_QUANT_ALLOWED_TEAM_TOOLS = frozenset({"send_message"})
_FIXED_QUANT_REQUIRED_MEMBERS = frozenset(
    {"quant-leader", "alpha_analyst", "risk_evidence_analyst"}
)
_FIXED_QUANT_ALLOWED_RAIL_SPEC_TYPES = frozenset(
    {
        RUNTIME_PROMPT,
        "swarm.response_prompt",
        "swarm.stream_event",
        CORE_SECURITY,
        CORE_HEARTBEAT,
        CONTEXT_PROCESSOR,
        TEAM_TOOL,
        TEAM_POLICY,
        CORE_OBSERVABILITY,
    }
)
_SUPPORTED_TEAM_TOOL_SURFACE = frozenset(
    {
        "approve_plan",
        "approve_tool",
        "async_task_cancel",
        "async_task_output",
        "async_tasks_list",
        "build_team",
        "claim_task",
        "clean_team",
        "create_task",
        "member_complete_task",
        "send_message",
        "shutdown_member",
        "spawn_bridge_agent",
        "spawn_external_cli",
        "spawn_human_agent",
        "spawn_teammate",
        "submit_plan",
        "swarmflow",
        "update_task",
        "view_task",
        "workspace_meta",
    }
)
_FORBIDDEN_FIXED_QUANT_RAIL_TYPES = frozenset(
    {
        "SkillUseRail",
        "SubagentRail",
        "SysOperationRail",
        "TaskPlanningRail",
        "TeamWorkspaceRail",
    }
)
_ORIGINAL_DEEP_AGENT_RESOLVE_PARTS: Any | None = None


def is_fixed_quant_team_identity(team_name: object, session_id: object) -> bool:
    """Match only the base quant team or its exact canonical session name."""

    normalized_team_name = str(team_name or "").strip()
    if normalized_team_name == "quant_team":
        return True

    session_suffix = re.sub(
        r"[^A-Za-z0-9_.-]+",
        "_",
        str(session_id or "").strip(),
    ).strip("._-")
    return bool(
        session_suffix
        and normalized_team_name == f"quant_team_{session_suffix}"
    )


def _is_fixed_quant_context(context: Any) -> bool:
    """Return whether a build context carries the fixed quant profile."""

    config = getattr(context, "config", None)
    return isinstance(config, dict) and config.get(_FIXED_QUANT_PROFILE_KEY) is True


def _assert_fixed_quant_upstream_compatibility() -> None:
    """Fail closed if the pinned openJiuwen capability surface drifts."""

    actual_version = distribution_version("openjiuwen")
    if actual_version != _SUPPORTED_OPENJIUWEN_VERSION:
        raise RuntimeError(
            "fixed quant capability adapter requires openjiuwen "
            f"{_SUPPORTED_OPENJIUWEN_VERSION}, got {actual_version}"
        )

    original = _ORIGINAL_DEEP_AGENT_RESOLVE_PARTS or DeepAgentSpec.resolve_parts
    parameters = tuple(inspect.signature(original).parameters)
    if parameters != ("self", "context"):
        raise RuntimeError(
            "openjiuwen DeepAgentSpec.resolve_parts signature changed; "
            f"expected ('self', 'context'), got {parameters}"
        )

    from openjiuwen.agent_teams.tools.tool_permissions import (
        HUMAN_AGENT_TOOLS,
        LEADER_TOOLS,
        MEMBER_TOOLS,
    )

    actual_surface = frozenset().union(
        HUMAN_AGENT_TOOLS,
        LEADER_TOOLS,
        MEMBER_TOOLS,
    )
    if actual_surface != _SUPPORTED_TEAM_TOOL_SURFACE:
        added = sorted(actual_surface - _SUPPORTED_TEAM_TOOL_SURFACE)
        removed = sorted(_SUPPORTED_TEAM_TOOL_SURFACE - actual_surface)
        raise RuntimeError(
            "openjiuwen team tool surface changed; fixed quant ceiling requires "
            f"review (added={added}, removed={removed})"
        )


class _InternalFixedQuantSysOperation(SysOperation):
    """Unregistered workspace-only operation with no agent-facing rail/tools."""

    def code(self) -> Any:
        raise RuntimeError("code execution is disabled for the fixed quant profile")

    def shell(self) -> Any:
        raise RuntimeError("shell is disabled for the fixed quant profile")


class _InternalFixedQuantSysOperationSpec:
    """Resolve a workspace-only object without registering sys-operation tools."""

    def __init__(self, member_id: str, workspace_root: str) -> None:
        self._member_id = member_id
        self._workspace_root = workspace_root

    def resolve(self) -> _InternalFixedQuantSysOperation:
        return _InternalFixedQuantSysOperation(
            SysOperationCard(
                id=f"{self._member_id}.fixed_quant_workspace",
                mode=OperationMode.LOCAL,
                work_config=LocalWorkConfig(
                    shell_allowlist=[],
                    sandbox_root=[self._workspace_root],
                    restrict_to_sandbox=True,
                ),
            )
        )


def _resolve_deep_agent_parts_with_fixed_quant_ceiling(
    spec: DeepAgentSpec,
    context: Any = None,
) -> Any:
    """Resolve a fixed member without upstream-injected generic capabilities."""

    original = _ORIGINAL_DEEP_AGENT_RESOLVE_PARTS
    if original is None:
        raise RuntimeError("fixed quant DeepAgentSpec adapter is not installed")
    if not _is_fixed_quant_context(context):
        return original(spec, context=context)

    _assert_fixed_quant_upstream_compatibility()
    card = getattr(spec, "card", None)
    member_id = str(getattr(card, "id", "") or "fixed_quant_member")
    workspace = getattr(spec, "workspace", None)
    workspace_root_value = str(
        getattr(workspace, "root_path", "") or ""
    ).strip()
    if not workspace_root_value:
        raise RuntimeError(
            "fixed quant capability ceiling requires a non-empty member workspace"
        )
    workspace_root = str(Path(workspace_root_value).expanduser().resolve())
    bounded_rails = [
        rail
        for rail in (spec.rails or [])
        if getattr(rail, "type", None) in _FIXED_QUANT_ALLOWED_RAIL_SPEC_TYPES
    ]
    bounded_spec = spec.model_copy(
        update={
            "add_general_purpose_agent": False,
            "approval_required_tools": [],
            "enable_async_subagent": False,
            "enable_skill_discovery": False,
            "enable_task_loop": False,
            "enable_task_planning": False,
            "mcps": [],
            # TeamAgentConfigurator injects core.sys_operation and
            # core.team.workspace after project enrichment. Retain only the
            # fixed prompt/safety rails, bounded team messaging/policy, and
            # no-op observability before upstream provider resolution.
            "rails": bounded_rails,
            "skills": [],
            "subagents": [],
            "sys_operation": _InternalFixedQuantSysOperationSpec(
                member_id,
                workspace_root,
            ),
        }
    )
    parts = original(bounded_spec, context=context)
    # openjiuwen 0.1.15.post3 hard-codes this value inside resolve_parts.
    # Reset the resolved config at the final project-owned seam.
    parts.config.enable_task_loop = False

    leaked_rails = sorted(
        {
            type(rail).__name__
            for rail in parts.rails
            if type(rail).__name__ in _FORBIDDEN_FIXED_QUANT_RAIL_TYPES
        }
    )
    if leaked_rails:
        raise RuntimeError(
            f"fixed quant capability ceiling leaked rails: {leaked_rails}"
        )
    return parts


class FixedQuantTeamPolicyRail(DeepAgentRail):
    """Minimal fixed-pipeline role and messaging policy without task-board text."""

    priority = 12

    def __init__(
        self,
        *,
        role: str,
        member_name: str,
        language: str,
        team_backend: Any = None,
    ) -> None:
        super().__init__()
        self._builder: Any = None
        self._team_backend = team_backend
        self._team_bootstrapped = False
        self._is_leader = str(role).strip().lower() == "leader"
        self._member_name = member_name
        role_name = "Coordinator" if role == "leader" else "Analyst"
        member = member_name or role_name
        self._section = PromptSection(
            name="fixed_quant_team_policy",
            content={
                "cn": (
                    "# 固定量化团队能力边界\n\n"
                    f"你的 member_name 是 `{member}`，角色是 {role_name}。"
                    "本轮唯一编排器是服务端八阶段量化状态机。只调用当前角色已暴露的 "
                    "Quant 工具；跨成员通信只使用 `send_message`。严格等待前一阶段 "
                    "`success=true` 后再继续。不得构建或清理团队，不得创建、查看、认领、"
                    "更新或完成任务，不得使用文件、shell、浏览器、子代理、技能或工作空间工具。\n"
                ),
                "en": (
                    "# Fixed Quant Team Capability Boundary\n\n"
                    f"Your member_name is `{member}` and your role is {role_name}. "
                    "The server-owned eight-stage quant state machine is the sole orchestrator. "
                    "Use only the Quant tools exposed for your role; use `send_message` only for "
                    "cross-member communication. Wait for `success=true` before the next stage. "
                    "Do not build or clean teams, manage tasks, or use file, shell, browser, "
                    "subagent, skill, or workspace capabilities.\n"
                ),
            },
            priority=11,
        )

    def init(self, agent: Any) -> None:
        super().init(agent)
        self._builder = getattr(agent, "system_prompt_builder", None)

    def uninit(self, agent: Any) -> None:
        if self._builder is not None:
            self._builder.remove_section(self._section.name)
        self._builder = None

    async def _ensure_fixed_team_bootstrapped(self) -> None:
        """Create the fixed roster server-side without exposing build_team."""

        if not self._is_leader or self._team_bootstrapped:
            return
        backend = self._team_backend
        if backend is None:
            raise RuntimeError(
                "fixed quant leader requires a team backend for roster bootstrap"
            )

        configured_members = {
            str(getattr(member, "member_name", "") or "").strip()
            for member in (getattr(backend, "predefined_members", None) or [])
        }
        configured_members.discard("")
        configured_members.add(
            str(getattr(backend, "member_name", "") or "").strip()
        )
        if configured_members != _FIXED_QUANT_REQUIRED_MEMBERS:
            raise RuntimeError(
                "fixed quant configured roster mismatch: "
                f"expected={sorted(_FIXED_QUANT_REQUIRED_MEMBERS)}, "
                f"actual={sorted(configured_members)}"
            )

        if await backend.get_team_info() is None:
            await backend.build_team(
                display_name="Fixed Quant Team",
                desc="Server-owned fixed eight-stage quant pipeline",
                leader_display_name=self._member_name or "quant-leader",
                leader_desc="Fixed quant pipeline coordinator",
            )

        actual_members = {
            str(getattr(member, "member_name", "") or "").strip()
            for member in await backend.list_members()
        }
        actual_members.discard("")
        actual_members.add(
            str(getattr(backend, "member_name", "") or "").strip()
        )
        if actual_members != _FIXED_QUANT_REQUIRED_MEMBERS:
            raise RuntimeError(
                "fixed quant runtime roster mismatch: "
                f"expected={sorted(_FIXED_QUANT_REQUIRED_MEMBERS)}, "
                f"actual={sorted(actual_members)}"
            )
        self._team_bootstrapped = True

    async def before_model_call(self, ctx: AgentCallbackContext) -> None:
        _ = ctx
        await self._ensure_fixed_team_bootstrapped()
        if self._builder is not None:
            self._builder.add_section(self._section)


def build_bounded_team_tool_rail(params: dict[str, Any], context: Any) -> Any:
    """Expose exactly send_message for fixed quant; delegate generic teams."""

    from openjiuwen.agent_teams.rails.elements import (
        TeamToolInput,
        build_team_tool_rail,
    )

    if not _is_fixed_quant_context(context):
        return build_team_tool_rail(params, context)

    _assert_fixed_quant_upstream_compatibility()
    backend = get_team_backend(context)
    if backend is None:
        return None

    from openjiuwen.agent_teams.rails.team_tool_rail import TeamToolRail

    inp = TeamToolInput.resolve(params, context)
    excluded = _SUPPORTED_TEAM_TOOL_SURFACE - _FIXED_QUANT_ALLOWED_TEAM_TOOLS
    return TeamToolRail(
        team_backend=backend,
        role=inp.role,
        teammate_mode=inp.teammate_mode,
        lifecycle=inp.lifecycle,
        language=inp.language,
        on_teammate_created=get_on_teammate_created(context),
        exclude_tools=set(excluded),
        workspace_manager=None,
        qualify_ids=inp.qualify_ids,
        team_name=inp.team_name,
        member_name=inp.member_name,
        messager=get_messager(context),
        team_permissions_enabled=inp.team_permissions_enabled,
    )


def build_bounded_team_policy_rail(params: dict[str, Any], context: Any) -> Any:
    """Replace task-oriented team policy only for the fixed quant profile."""

    from openjiuwen.agent_teams.rails.elements import build_team_policy_rail

    if not _is_fixed_quant_context(context):
        return build_team_policy_rail(params, context)

    _assert_fixed_quant_upstream_compatibility()
    backend = get_team_backend(context)
    return FixedQuantTeamPolicyRail(
        role=str(getattr(context, "role", "") or "teammate"),
        member_name=str(getattr(context, "member_name", "") or ""),
        language=str(getattr(context, "language", "") or "cn"),
        team_backend=backend,
    )


def install_fixed_quant_runtime_adapters() -> None:
    """Install idempotent fixed-context adapters at public registry seams."""

    global _ORIGINAL_DEEP_AGENT_RESOLVE_PARTS
    if _ORIGINAL_DEEP_AGENT_RESOLVE_PARTS is None:
        _ORIGINAL_DEEP_AGENT_RESOLVE_PARTS = DeepAgentSpec.resolve_parts

        @wraps(_ORIGINAL_DEEP_AGENT_RESOLVE_PARTS)
        def resolve_parts(
            spec: DeepAgentSpec,
            context: Any = None,
        ) -> Any:
            return _resolve_deep_agent_parts_with_fixed_quant_ceiling(
                spec,
                context=context,
            )

        DeepAgentSpec.resolve_parts = resolve_parts

    # openjiuwen's provider registry intentionally uses last registration wins.
    register_rail_provider(TEAM_TOOL, build_bounded_team_tool_rail)
    register_rail_provider(TEAM_POLICY, build_bounded_team_policy_rail)


def _workspace_root(ctx: SwarmBuildContext) -> str | None:
    """Resolve the member workspace root path."""
    workspace = getattr(ctx, "workspace", None)
    return getattr(workspace, "root_path", None) if workspace else None


class SkillRetrievalPromptInput(ConstructionInput):
    """Construction inputs for the agentic skill retrieval prompt rail."""

    global_skills_dir: str | None = context_field(
        attr="global_skills_dir",
        description="Global installed skills source directory.",
    )


@harness_element(
    kind=ElementKind.RAIL,
    name=SKILL_RETRIEVAL_PROMPT,
    description="Lightweight prompt guidance for agentic installed-skill tree retrieval.",
    input_model=SkillRetrievalPromptInput,
)
def _build_skill_retrieval_prompt_rail(
    params: dict[str, Any],
    context: SwarmBuildContext,
) -> SkillRetrievalPromptRail | None:
    """Build the skill retrieval prompt rail when the feature is enabled."""
    from jiuwenswarm.agents.harness.common.tools.skill_retrieval_toolkits import (
        is_skill_retrieval_enabled,
    )
    from jiuwenswarm.agents.swarm.providers.tools import visible_skill_names_for_list_skill
    from jiuwenswarm.server.runtime.skill.skill_manager import SkillManager

    if not is_skill_retrieval_enabled():
        return None
    SkillRetrievalPromptInput.resolve(params, context)
    manager = SkillManager()
    return SkillRetrievalPromptRail(
        manager=manager,
        visible_skill_names=lambda: visible_skill_names_for_list_skill(context),
    )


@harness_element(
    kind=ElementKind.RAIL,
    name=SYMPHONY_ORCHESTRATION_PROMPT,
    description="Leader-only prompt guidance for Symphony orchestration.",
)
def _build_symphony_orchestration_prompt_rail(
    params: dict[str, Any],
    context: SwarmBuildContext,
) -> SymphonyOrchestrationPromptRail | None:
    """Build the Symphony orchestration prompt rail for the team leader."""
    _ = params
    if getattr(context, "role", "") != "leader":
        return None
    return SymphonyOrchestrationPromptRail()


class RuntimePromptInput(ConstructionInput):
    """Construction inputs for the member runtime prompt rail."""

    language: str = context_field(
        attr="language",
        default="cn",
        description="Resolved member language code.",
    )
    channel: str = context_field(
        attr="channel",
        default="default",
        description="Resolved channel key.",
    )
    project_dir: str | None = context_field(
        attr="project_dir",
        description="Resolved user project directory (seeds the TUI cwd policy).",
    )


@harness_element(
    kind=ElementKind.RAIL,
    name=RUNTIME_PROMPT,
    description="Per-member runtime prompt rail bound to the member's language and channel.",
    input_model=RuntimePromptInput,
)
def _build_runtime_prompt_rail(
    params: dict[str, Any],
    context: SwarmBuildContext,
) -> RuntimePromptRail:
    """Build the runtime prompt rail for a member.

    Args:
        params: Spec params (unused; kept for the provider contract).
        context: Per-member build context.

    Returns:
        A ``RuntimePromptRail`` bound to the member's language and channel.
    """
    inp = RuntimePromptInput.resolve(params, context)
    rail = RuntimePromptRail(language=inp.language, channel=inp.channel)
    # Seed cwd/project_dir so the TUI branch injects the "current project
    # directory" policy and the model answers with the project dir instead of
    # calling `pwd` (which would surface the per-member workspace path).
    # Mirrors the code-team rail (code_rails.build_code_runtime_prompt).
    if inp.project_dir:
        rail.set_runtime_paths(cwd=inp.project_dir, project_dir=inp.project_dir)
    return rail


class TeamSkillStoragePolicyInput(ConstructionInput):
    """Construction inputs for the team skill storage policy rail."""

    global_skills_dir: str | None = context_field(
        attr="global_skills_dir",
        description="Global shared skills source directory.",
    )
    team_ws_root: str | None = context_field(
        attr="team_ws_root",
        description="Team shared workspace root.",
    )
    team_skills_dir: str | None = context_field(
        attr="team_skills_dir",
        description="Team shared skills linked view.",
    )
    member_workspace_root: str | None = context_field(
        resolver=_workspace_root,
        description="Current member workspace root.",
    )


@harness_element(
    kind=ElementKind.RAIL,
    name=TEAM_SKILL_STORAGE_POLICY,
    description="Team-only policy that stores all skill authoring outputs in "
    "the global shared skills source directory.",
    input_model=TeamSkillStoragePolicyInput,
)
def _build_team_skill_storage_policy_rail(
    params: dict[str, Any],
    context: SwarmBuildContext,
) -> TeamSkillStoragePolicyRail | None:
    """Build the team skill storage policy rail when the global skill root exists.

    Args:
        params: Spec params (unused; kept for the provider contract).
        context: Per-member build context.

    Returns:
        A ``TeamSkillStoragePolicyRail`` or ``None`` when no global skills
        directory is available.
    """
    inp = TeamSkillStoragePolicyInput.resolve(params, context)
    if not inp.global_skills_dir:
        return None
    return TeamSkillStoragePolicyRail(
        global_skills_dir=inp.global_skills_dir,
        team_workspace_root=inp.team_ws_root,
        team_skills_dir=inp.team_skills_dir,
        member_workspace_root=inp.member_workspace_root,
    )


class TeamSharedSkillLinkRefreshInput(ConstructionInput):
    """Construction inputs for refreshing team shared skill links."""

    global_skills_dir: str | None = context_field(
        attr="global_skills_dir",
        description="Global shared skills source directory.",
    )
    session_id: str = context_field(
        attr="session_id",
        default="",
        description="Active session id.",
    )
    channel: str = context_field(
        attr="channel",
        default="default",
        description="Resolved channel key for the per-channel team manager.",
    )


@harness_element(
    kind=ElementKind.RAIL,
    name=TEAM_SHARED_SKILL_LINK_REFRESH,
    description="Refresh team shared skill links after tools write into the "
    "global shared skills source directory.",
    input_model=TeamSharedSkillLinkRefreshInput,
)
def _build_team_shared_skill_link_refresh_rail(
    params: dict[str, Any],
    context: SwarmBuildContext,
) -> TeamSharedSkillLinkRefreshRail | None:
    """Build the rail that refreshes team shared skill links after writes.

    Args:
        params: Spec params (unused; kept for the provider contract).
        context: Per-member build context.

    Returns:
        A ``TeamSharedSkillLinkRefreshRail`` or ``None`` when required runtime
        context is missing.
    """
    inp = TeamSharedSkillLinkRefreshInput.resolve(params, context)
    if not inp.global_skills_dir or not inp.session_id:
        return None

    def refresh_links() -> None:
        """Refresh the current team's shared skill link view."""
        from jiuwenswarm.agents.harness.team.team_manager import get_team_manager

        get_team_manager(inp.channel).refresh_team_shared_skill_links(inp.session_id)

    return TeamSharedSkillLinkRefreshRail(
        global_skills_dir=Path(inp.global_skills_dir),
        refresh_links=refresh_links,
    )


class TeamWorkspaceReportPathInput(ConstructionInput):
    """Construction inputs for the team workspace report-path rail."""

    team_ws_root: str | None = context_field(
        attr="team_ws_root",
        description="Team shared workspace root path (gate; skipped when absent).",
    )
    team_id: str = context_field(attr="team_id", default="", description="Team name.")
    language: str = context_field(
        attr="language",
        default="cn",
        description="Resolved member language code.",
    )


@harness_element(
    kind=ElementKind.RAIL,
    name=TEAM_WORKSPACE_REPORT_PATH,
    description="Rewrites report paths under the shared team workspace root "
    "(skipped when no shared root is configured).",
    input_model=TeamWorkspaceReportPathInput,
)
def _build_team_workspace_report_path_rail(
    params: dict[str, Any],
    context: SwarmBuildContext,
) -> TeamWorkspaceReportPathRail | None:
    """Build the team workspace report-path rail when a shared root exists.

    Args:
        params: Spec params (unused; kept for the provider contract).
        context: Per-member build context.

    Returns:
        A ``TeamWorkspaceReportPathRail`` rooted at the team workspace, or
        ``None`` when no shared workspace root is configured.
    """
    inp = TeamWorkspaceReportPathInput.resolve(params, context)
    if not inp.team_ws_root:
        return None
    return TeamWorkspaceReportPathRail(
        root_dir=inp.team_ws_root,
        team_id=inp.team_id,
        language=inp.language,
    )


class ContextProcessorInput(ConstructionInput):
    """Construction inputs for the context-compression rail."""

    context_engine_enabled: bool = param_field(
        default=True,
        description="Whether the context engine is enabled in config (gate).",
    )
    context_engine_config: dict[str, Any] = param_field(
        default_factory=dict,
        description="Context-engine config (compressor sub-configs).",
    )


@harness_element(
    kind=ElementKind.RAIL,
    name=CONTEXT_PROCESSOR,
    description="Context-compression rail, mounted only when the context engine "
    "is enabled in config.",
    input_model=ContextProcessorInput,
)
def _build_context_processor(
    params: dict[str, Any],
    context: SwarmBuildContext,
) -> Any | None:
    """Build the context-compression rail when the context engine is enabled.

    Args:
        params: Spec params (unused; kept for the provider contract).
        context: Per-member build context.

    Returns:
        A preset ``ContextProcessorRail`` when enabled, otherwise ``None``.
    """
    inp = ContextProcessorInput.resolve(params, context)
    if not inp.context_engine_enabled:
        return None
    return _build_context_processor_rail(
        {"context_engine_config": inp.context_engine_config}
    )


@harness_element(
    kind=ElementKind.RAIL,
    name=PLUGIN_RAILS,
    description="User-registered extension rails: a fresh instance of every "
    "registered rail extension, one per member.",
)
def _build_plugin_rails(
    params: dict[str, Any],
    context: SwarmBuildContext,
) -> list[Any]:
    """Build user-registered extension rails for a member.

    Enumerates every registered rail extension and instantiates a fresh
    instance per member, skipping any that fail to load.

    Args:
        params: Spec params (unused; kept for the provider contract).
        context: Per-member build context.

    Returns:
        A list of extension rail instances (possibly empty).
    """
    rail_manager = get_rail_manager()
    rails: list[Any] = []
    for rail_name in rail_manager.get_registered_rail_names():
        try:
            rail_instance = rail_manager.load_rail_instance_without_enabled_check(
                rail_name,
            )
            if rail_instance is not None:
                rails.append(rail_instance)
        except Exception as exc:
            logger.warning(
                "[SwarmRails] load extension rail %s failed: %s",
                rail_name,
                exc,
            )
    return rails


__all__ = [
    "RUNTIME_PROMPT",
    "TEAM_SKILL_STORAGE_POLICY",
    "TEAM_SHARED_SKILL_LINK_REFRESH",
    "TEAM_WORKSPACE_REPORT_PATH",
    "CONTEXT_PROCESSOR",
    "PLUGIN_RAILS",
    "SKILL_RETRIEVAL_PROMPT",
    "SYMPHONY_ORCHESTRATION_PROMPT",
    "TEAM_PERMISSION",
    "TEAM_PERMISSION_POLICY",
]


# ---------------------------------------------------------------------------
# team.permission_policy — TeamPermissionPolicyRail (leader prompt section)
# ---------------------------------------------------------------------------


TEAM_PERMISSION_POLICY = "swarm.team_permission_policy"


class TeamPermissionPolicyInput(ConstructionInput):
    """Construction inputs for the team permission policy prompt rail."""

    permissions_config: dict[str, Any] = param_field(
        default_factory=dict,
        description="Permission config dict used to generate permission "
        "rule descriptions via format_base_permissions_for_desc.",
    )
    language: str = context_field(
        attr="language",
        default="cn",
        description="Resolved member language code.",
    )


@harness_element(
    kind=ElementKind.RAIL,
    name=TEAM_PERMISSION_POLICY,
    description="Injects teammate permission rules into the leader's system prompt.",
    input_model=TeamPermissionPolicyInput,
)
def _build_team_permission_policy_rail(
    params: dict[str, Any],
    context: SwarmBuildContext,
) -> Any | None:
    """Build the permission policy prompt rail for the leader."""
    inp = TeamPermissionPolicyInput.resolve(params, context)
    if not inp.permissions_config.get("enabled"):
        return None

    from jiuwenswarm.agents.harness.team.rails.team_permission_policy_rail import (
        TeamPermissionPolicyRail,
    )

    return TeamPermissionPolicyRail(
        permissions_config=inp.permissions_config,
        language=inp.language,
    )


# ---------------------------------------------------------------------------
# team.permission — TeamPermissionRail (swarm-side thin provider)
# ---------------------------------------------------------------------------


TEAM_PERMISSION = "swarm.team_permission"


class TeamPermissionInput(ConstructionInput):
    """Construction inputs for the team permission rail."""

    permissions_config: dict[str, Any] = param_field(
        default_factory=dict,
        description="Full permission config dict (as consumed by "
        "openjiuwen.harness.security.engine.PermissionEngine).",
    )


@harness_element(
    kind=ElementKind.RAIL,
    name=TEAM_PERMISSION,
    description="Team-mode permission guardrail with leader-mediated ASK resolution.",
    input_model=TeamPermissionInput,
)
def _build_team_permission_rail(params: dict[str, Any], context: Any) -> Any | None:
    """Build the team permission rail (gated on backend + messager + permissions enabled).

    Thin swarm provider: reads ``permissions_config`` from ``RailSpec.params``
    (baked by config_specs) and runtime handles from ``BuildContext.extras``
    (injected by AgentConfigurator). The actual permission logic —
    openjiuwen.harness.security.engine.PermissionEngine,
    openjiuwen.agent_teams.rails.team_permission_rail.TeamPermissionRail,
    openjiuwen.agent_teams.rails.team_permission_rail.TeamApprovalOrchestrator —
    lives in openjiuwen.
    """
    backend = get_team_backend(context)
    messager = get_messager(context)
    if backend is None or messager is None:
        return None

    inp = TeamPermissionInput.resolve(params, context)
    if not inp.permissions_config.get("enabled"):
        return None

    from openjiuwen.agent_teams.rails.team_permission_rail import (
        TeamApprovalOrchestrator,
        TeamPermissionRail,
    )
    from openjiuwen.agent_teams.tools.message_manager import TeamMessageManager
    from openjiuwen.harness.security.host import ToolPermissionHost
    from openjiuwen.agent_teams.security.narrowing import narrow_permissions

    override = get_permissions_override(context)
    narrowed_config = narrow_permissions(inp.permissions_config, override) if override else inp.permissions_config

    message_manager = TeamMessageManager(
        backend.team_name,
        backend.member_name,
        backend.db,
        messager,
    )
    orchestrator = TeamApprovalOrchestrator(
        message_manager=message_manager,
        leader_member_name=backend.leader_member_name,
    )

    host = ToolPermissionHost(
        request_permission_confirmation=orchestrator.handle_approval_request,
    )

    return TeamPermissionRail(
        config=narrowed_config,
        host=host,
    )
