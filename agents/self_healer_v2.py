
from __future__ import annotations

import traceback
from typing import Any

from agents.base_agent import BaseAgent, TaskResult
from modules.apply_engine import ApplyEngine
from modules.evolution_archive import EvolutionArchive
from modules.evolution_events import EvolutionEventStore
from modules.sandbox_manager import SandboxManager


class SelfHealerV2(BaseAgent):
    NEEDS = {
        'heal': ['devops_agent', 'quality_judge', 'reflector'],
        '*': ['reflector'],
    }

    def __init__(self, *, sandbox_manager: SandboxManager, apply_engine: ApplyEngine, reflector=None, archive: EvolutionArchive | None = None, legacy_healer=None, event_store: EvolutionEventStore | None = None, **kwargs):
        super().__init__(name='self_healer_v2', description='Sandbox-first self-healing engine', **kwargs)
        self.sandbox_manager = sandbox_manager
        self.apply_engine = apply_engine
        self.reflector = reflector
        self.archive = archive or EvolutionArchive()
        self.legacy_healer = legacy_healer
        self.event_store = event_store or EvolutionEventStore()

    @property
    def capabilities(self) -> list[str]:
        return ['heal']

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        if task_type != 'heal':
            return TaskResult(success=False, error=f'unsupported task_type={task_type}')
        try:
            result = await self.heal(kwargs.get('error'), kwargs.get('context') or {}, kwargs.get('patch_files') or {})
            return TaskResult(success=bool(result.get('success')), output=result, error='' if result.get('success') else str(result.get('error') or 'heal-failed'))
        except Exception as exc:
            return TaskResult(success=False, error=str(exc))

    async def handle_error(self, agent: str, error: Exception, context: dict[str, Any] | None = None) -> dict[str, Any]:
        ctx = dict(context or {})
        patch_files = dict(ctx.get("patch_files") or {})
        task_root_id = str(ctx.get("task_root_id") or "")[:120]
        if patch_files:
            result = await self.heal(error, ctx, patch_files)
            self.event_store.record_event(
                event_type="self_heal_v2",
                source="self_healer_v2",
                title=f"{agent}:{type(error).__name__}",
                status="ok" if result.get("success") else "failed",
                severity="warning" if result.get("success") else "error",
                payload={"agent": agent, "result": result},
                task_root_id=task_root_id,
            )
            self.archive.record(
                archive_type="self_heal_v2",
                title=f"{agent}:{type(error).__name__}",
                payload={"agent": agent, "result": result, "context": ctx},
                success=bool(result.get("success")),
                task_root_id=task_root_id,
            )
            return result
        if self.legacy_healer is not None:
            legacy = await self.legacy_healer.handle_error(agent, error, ctx)
            self.event_store.record_event(
                event_type="self_heal_legacy_bridge",
                source="self_healer_v2",
                title=f"{agent}:{type(error).__name__}",
                status="ok" if legacy.get("resolved") else "failed",
                severity="warning",
                payload={"agent": agent, "result": legacy},
                task_root_id=task_root_id,
            )
            self.archive.record(
                archive_type="self_heal_legacy_bridge",
                title=f"{agent}:{type(error).__name__}",
                payload={"agent": agent, "result": legacy, "context": ctx},
                success=bool(legacy.get("resolved")),
                task_root_id=task_root_id,
            )
            return legacy
        result = {
            "resolved": False,
            "method": "no_patch_no_legacy",
            "description": "v2 self-healer has no patch_files and no legacy healer fallback",
        }
        self.archive.record(
            archive_type="self_heal_v2",
            title=f"{agent}:{type(error).__name__}",
            payload={"agent": agent, "result": result, "context": ctx},
            success=False,
            task_root_id=task_root_id,
        )
        self.event_store.record_event(
            event_type="self_heal_v2",
            source="self_healer_v2",
            title=f"{agent}:{type(error).__name__}",
            status="failed",
            severity="error",
            payload={"agent": agent, "result": result},
            task_root_id=task_root_id,
        )
        return result

    async def heal(self, error: Any, context: dict[str, Any], patch_files: dict[str, str]) -> dict[str, Any]:
        tb = traceback.format_exc()
        sandbox_id, sandbox_path = await self.sandbox_manager.create()
        try:
            async def _patch(path):
                for rel, content in (patch_files or {}).items():
                    target = path / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(content)
            sandbox_result = await self.sandbox_manager.run_in_sandbox(sandbox_path, _patch)
            if not sandbox_result.success:
                return {
                    'success': False,
                    'stage': 'sandbox',
                    'sandbox_id': sandbox_id,
                    'error': sandbox_result.error or 'sandbox failed',
                    'traceback': tb[-1000:],
                }
            apply_result = await self.apply_engine.apply_files(patch_files or {}, health_check=context.get('health_check'))
            payload = {
                'success': bool(apply_result.success),
                'stage': 'apply' if apply_result.success else 'rollback',
                'sandbox_id': sandbox_id,
                'snapshot_id': apply_result.snapshot_id,
                'applied_files': apply_result.applied_files,
                'health_ok': apply_result.health_ok,
                'rollback_performed': apply_result.rollback_performed,
                'details': apply_result.details,
            }
            if self.reflector and hasattr(self.reflector, 'reflect'):
                try:
                    maybe = self.reflector.reflect(
                        category='technical',
                        action_type='self_healer_v2',
                        input_summary=str(context)[:500],
                        outcome_summary=str(payload)[:1000],
                        success=bool(payload.get("success")),
                        context={"source": "self_healer_v2", "factors": ["sandbox", "apply_engine"]},
                    )
                    if hasattr(maybe, '__await__'):
                        await maybe
                except Exception:
                    pass
            self.archive.record(
                archive_type="self_heal_v2",
                title=str(type(error).__name__ if error else "unknown_error"),
                payload={"context": context, "result": payload},
                success=bool(payload.get("success")),
                task_root_id=str(context.get("task_root_id") or "")[:120],
            )
            return payload
        finally:
            await self.sandbox_manager.destroy(sandbox_path)
