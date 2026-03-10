
from __future__ import annotations

import traceback
from typing import Any

from agents.base_agent import BaseAgent, TaskResult
from modules.apply_engine import ApplyEngine
from modules.sandbox_manager import SandboxManager


class SelfHealerV2(BaseAgent):
    NEEDS = {
        'heal': ['devops_agent', 'quality_judge', 'reflector'],
        '*': ['reflector'],
    }

    def __init__(self, *, sandbox_manager: SandboxManager, apply_engine: ApplyEngine, reflector=None, **kwargs):
        super().__init__(name='self_healer_v2', description='Sandbox-first self-healing engine', **kwargs)
        self.sandbox_manager = sandbox_manager
        self.apply_engine = apply_engine
        self.reflector = reflector

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
                        title='self_healer_v2',
                        content=str(payload),
                    )
                    if hasattr(maybe, '__await__'):
                        await maybe
                except Exception:
                    pass
            return payload
        finally:
            await self.sandbox_manager.destroy(sandbox_path)
