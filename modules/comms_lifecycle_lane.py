from __future__ import annotations

from telegram.error import Conflict as TgConflict
from telegram.ext import ContextTypes

from config.logger import get_logger

logger = get_logger(__name__)


def set_modules(
    agent,
    *,
    goal_engine=None,
    llm_router=None,
    decision_loop=None,
    agent_registry=None,
    self_healer=None,
    self_updater=None,
    conversation_engine=None,
    judge_protocol=None,
    finance=None,
    skill_registry=None,
    weekly_planner=None,
    schedule_manager=None,
    publisher_queue=None,
    cancel_state=None,
    owner_task_state=None,
) -> None:
    agent._goal_engine = goal_engine
    agent._llm_router = llm_router
    agent._decision_loop = decision_loop
    agent._agent_registry = agent_registry
    if self_healer is not None:
        agent._self_healer = self_healer
    if self_updater is not None:
        agent._self_updater = self_updater
    if conversation_engine is not None:
        agent._conversation_engine = conversation_engine
    if judge_protocol is not None:
        agent._judge_protocol = judge_protocol
    if finance is not None:
        agent._finance = finance
    if skill_registry is not None:
        agent._skill_registry = skill_registry
    if weekly_planner is not None:
        agent._weekly_planner = weekly_planner
    if schedule_manager is not None:
        agent._schedule_manager = schedule_manager
    if publisher_queue is not None:
        agent._publisher_queue = publisher_queue
    if cancel_state is not None:
        agent._cancel_state = cancel_state
    if owner_task_state is not None:
        agent._owner_task_state = owner_task_state


async def on_app_error(agent, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = getattr(context, 'error', None)
    if isinstance(err, TgConflict):
        if agent._telegram_conflict_mode:
            return
        agent._telegram_conflict_mode = True
        logger.error(
            'Telegram polling conflict detected; switching to degraded mode (owner_inbox fallback).',
            extra={'event': 'telegram_conflict_mode'},
        )
        try:
            if agent._app and agent._app.updater:
                await agent._app.updater.stop()
        except Exception:
            pass
        try:
            from modules.owner_inbox import write_outbox
            write_outbox(
                '⚠️ Telegram Conflict: другой инстанс использует getUpdates. '
                'VITO переключен в fallback owner_inbox до устранения конфликта.'
            )
        except Exception:
            pass


async def stop(agent) -> None:
    if agent._app and agent._app.updater.running:
        await agent._app.updater.stop()
        await agent._app.stop()
        await agent._app.shutdown()
        logger.info('Telegram бот остановлен', extra={'event': 'bot_stopped'})
