from __future__ import annotations

import asyncio
import json
from typing import Any

from config import settings
from modules.conversation_autonomy_action_lane import handle_autonomy_action as _handle_autonomy_action_impl


async def dispatch_action_legacy(engine, action: str, params: dict) -> str:
    """Legacy action router extracted from ConversationEngine."""

    autonomy_result = await _handle_autonomy_action_impl(engine, action, params)
    if autonomy_result is not None:
        return autonomy_result

    if action == "dispatch_agent" and engine.agent_registry:
        task_type = params.get("task_type", "")
        clean_params = {k: v for k, v in params.items() if k != "task_type"}
        result = await engine.agent_registry.dispatch(task_type, **clean_params)
        if result and result.success:
            out_text = str(result.output)[:300]
            quality_scoped = {
                "research",
                "social_media",
                "content_creation",
                "documentation",
                "listing_seo_pack",
                "publish",
                "product_pipeline",
            }
            if str(task_type or "").strip().lower() in quality_scoped:
                q = await engine._maybe_quality_gate(str(task_type), str(clean_params)[:250], str(result.output)[:5000])
                return f"Агент выполнил: {out_text}\nQuality gate: {q}"
            return f"Агент выполнил: {out_text}"
        return f"Агент не смог выполнить: {result.error if result else 'нет агента'}"

    if action == "scan_trends" and engine.agent_registry:
        result = await engine.agent_registry.dispatch("trend_scan", **params)
        return f"Тренды: {str(result.output)[:300]}" if result and result.success else "Сканирование не удалось"

    if action == "scan_reddit" and engine.agent_registry:
        result = await engine.agent_registry.dispatch("reddit_scan", **params)
        return f"Reddit: {str(result.output)[:300]}" if result and result.success else "Сканирование не удалось"

    if action == "cancel_goal" and engine.goal_engine:
        goal_id = params.get("goal_id", "")
        if engine.goal_engine.delete_goal(goal_id):
            return f"Цель {goal_id} удалена"
        engine.goal_engine.fail_goal(goal_id, "Отменено владельцем")
        return f"Цель {goal_id} отменена (не удалось удалить)"

    if action == "change_priority" and engine.goal_engine:
        from goal_engine import GoalPriority
        goal_id = params.get("goal_id", "")
        priority = params.get("priority", "MEDIUM")
        goal = engine.goal_engine._goals.get(goal_id)
        if goal:
            goal.priority = GoalPriority[priority.upper()]
            return f"Приоритет {goal_id} → {priority}"
        return f"Цель {goal_id} не найдена"

    if action == "stop_loop" and engine.decision_loop:
        engine.decision_loop.stop()
        return "Decision Loop остановлен"

    if action == "start_loop" and engine.decision_loop:
        if not engine.decision_loop.running:
            asyncio.create_task(engine.decision_loop.run())
            return "Decision Loop запущен"
        return "Decision Loop уже работает"

    if action == "check_errors" and engine.self_healer:
        stats = engine.self_healer.get_error_stats()
        return f"Ошибок: {stats['total']}, решено: {stats['resolved']}, нерешено: {stats['unresolved']}"

    if action == "analyze_niche" and engine.judge_protocol:
        topic = params.get("topic", "digital products")
        deep = params.get("deep", False)
        if deep:
            verdict = await engine.judge_protocol.evaluate_niche_deep(topic)
        else:
            verdict = await engine.judge_protocol.evaluate_niche(topic)
        return engine.judge_protocol.format_verdict_for_telegram(verdict)

    if action == "update_knowledge" and engine.knowledge_updater:
        results = await engine.knowledge_updater.run_weekly_update()
        return f"Знания обновлены: {json.dumps(results, ensure_ascii=False)[:200]}"

    if action == "create_backup" and engine.self_updater:
        path = engine.self_updater.backup_current_code()
        return f"Бэкап: {path}" if path else "Бэкап не удался"

    if action == "apply_code_change" and engine.code_generator:
        target_file = params.get("file", "")
        instruction = params.get("instruction", "")
        if not target_file or not instruction:
            return "Нужны параметры: file и instruction"
        result = await engine.code_generator.apply_change(target_file, instruction)
        if result.get("success"):
            return f"Код изменён: {target_file}"
        return f"Не удалось изменить: {result.get('error', 'unknown')}"

    if action == "self_improve" and engine.agent_registry:
        request = params.get("request", "") or params.get("instruction", "")
        if not request:
            return "Нужен параметр: request"
        result = await engine.agent_registry.dispatch("self_improve", step=request)
        if result and result.success:
            return "Self-improve завершён успешно"
        return f"Self-improve завершён с ошибкой: {getattr(result, 'error', 'unknown')}"

    if action == "learn_service" and engine.agent_registry:
        service = params.get("service", "") or params.get("name", "")
        if not service:
            return "Нужен параметр: service"
        result = await engine.agent_registry.dispatch(
            "research_platform",
            service=service,
            platform_name=service,
            platform_url=params.get("platform_url") or params.get("url"),
        )
        if result and result.success:
            return f"Знания по сервису {service} обновлены"
        return f"Не удалось изучить сервис: {getattr(result, 'error', 'unknown')}"

    if action == "onboard_platform" and engine.agent_registry:
        platform_name = params.get("platform_name", "") or params.get("service", "") or params.get("name", "")
        platform_url = params.get("platform_url") or params.get("url")
        if not platform_name:
            return "Нужен параметр: platform_name"
        result = await engine.agent_registry.dispatch(
            "onboard_platform",
            platform_name=platform_name,
            platform_url=platform_url,
        )
        if result and result.success:
            output = result.output if isinstance(result.output, dict) else {}
            return (
                f"Онбординг платформы {platform_name} завершён. "
                f"Статус: {output.get('status', 'active')}, platform_id={output.get('platform_id', '?')}"
            )
        return f"Не удалось подключить платформу: {getattr(result, 'error', 'unknown')}"

    if action == "run_deep_research" and engine.agent_registry:
        topic = str(params.get("topic") or "digital products").strip()
        task_root_id = ""
        if engine.owner_task_state:
            try:
                active = engine.owner_task_state.get_active() or {}
                task_root_id = str(active.get("task_root_id") or "").strip()
            except Exception:
                task_root_id = ""
        result = await engine.agent_registry.dispatch(
            "research",
            step=topic,
            topic=topic,
            task_root_id=task_root_id,
            goal_title=f"Deep research: {topic[:80]}",
        )
        if result and (result.success or getattr(result, "output", None)):
            meta = getattr(result, "metadata", {}) or {}
            summary = str(meta.get("executive_summary") or str(result.output)[:1200])
            sources = list(meta.get("data_sources") or [])
            report_path = str(meta.get("report_path") or "").strip()
            top_ideas = list(meta.get("top_ideas") or [])
            recommended_product = meta.get("recommended_product") if isinstance(meta.get("recommended_product"), dict) else {}
            verdict = "unknown"
            score = 0
            try:
                q = await engine.agent_registry.dispatch(
                    "quality_review",
                    content=str(result.output)[:6000],
                    content_type="deep_research_report",
                )
                if q and q.success and isinstance(getattr(q, "output", None), dict):
                    qout = q.output
                    score = int(qout.get("score", 0) or 0)
                    verdict = "ok" if bool(qout.get("approved", False)) else "rework"
            except Exception:
                pass
            if engine.owner_task_state:
                try:
                    engine.owner_task_state.enrich_active(
                        research_topic=topic[:200],
                        research_report_path=report_path,
                        research_quality_score=score,
                        research_options_json=json.dumps(top_ideas, ensure_ascii=False),
                        research_recommended_json=json.dumps(recommended_product, ensure_ascii=False),
                        selected_research_title=str((recommended_product or {}).get("title") or "")[:180],
                    )
                except Exception:
                    pass
            return engine._format_deep_research_owner_report(
                topic=topic,
                summary=summary,
                score=score,
                verdict=verdict,
                sources=sources,
                report_path=report_path,
                top_ideas=top_ideas,
                recommended_product=recommended_product,
            )
        return f"Глубокое исследование не удалось: {getattr(result, 'error', 'unknown')}"

    if action == "run_product_pipeline" and engine.agent_registry:
        topic = str(params.get("topic") or "Digital Product").strip()
        platforms = params.get("platforms") or [params.get("platform", "gumroad")]
        if isinstance(platforms, str):
            platforms = [p.strip() for p in platforms.split(",") if p.strip()]
        if not isinstance(platforms, list) or not platforms:
            platforms = ["gumroad"]
        auto_publish = bool(params.get("auto_publish", False))
        res = await engine.agent_registry.dispatch(
            "product_pipeline",
            topic=topic,
            platform=",".join(platforms),
            auto_publish=auto_publish,
        )
        if res and res.success:
            out = getattr(res, "output", {}) or {}
            done = len([s for s in (out.get("steps") or []) if s.get("ok")])
            total = len(out.get("steps") or [])
            q = await engine._maybe_quality_gate("product_pipeline", topic, json.dumps(out, ensure_ascii=False)[:5000])
            return (
                f"Product pipeline завершён: {done}/{total} шагов выполнено.\n"
                f"Quality gate: {q}\n"
                f"Artifacts: {str(out.get('artifacts') or '')[:500]}"
            )
        return f"Product pipeline не удался: {getattr(res, 'error', 'unknown')}"

    if action == "run_social_pack" and engine.agent_registry:
        topic = str(params.get("topic") or "Product").strip()
        platform = str(params.get("platform") or "twitter").strip().lower()
        content = str(params.get("content") or topic).strip()
        res = await engine.agent_registry.dispatch("social_media", platform=platform, content=content)
        if res and res.success:
            q = await engine._maybe_quality_gate("social_media", content, str(getattr(res, "output", ""))[:5000])
            return f"Соцпакет для {platform} подготовлен. Quality gate: {q}"
        return f"Соцпакет не удался: {getattr(res, 'error', 'unknown')}"

    if action == "execute_autonomy_proposal":
        proposal = params.get("proposal") if isinstance(params.get("proposal"), dict) else {}
        title = str(proposal.get("title") or params.get("title") or "Автономная задача").strip()[:180] or "Автономная задача"
        description = str(proposal.get("description") or params.get("description") or title).strip()[:500]
        proposal_id = 0
        if engine.autonomy_proposals and isinstance(params.get("proposal_id"), int):
            proposal_id = int(params.get("proposal_id") or 0)
        if engine.goal_engine:
            engine.goal_engine.add_goal(
                title,
                description,
                source="autonomy_proposal",
                metadata={"proposal": proposal},
                estimated_roi=float(proposal.get("expected_revenue") or 0),
            )
        if proposal_id > 0:
            try:
                engine.autonomy_proposals.mark_status(proposal_id, "executed", note="goal_created_via_conversation_engine")
            except Exception:
                pass
        return f"Автономное предложение запущено: {title}"

    if action == "run_improvement_cycle":
        request = str(params.get("request") or "").strip()
        lines: list[str] = []
        if engine.self_updater:
            try:
                bkp = engine.self_updater.backup_current_code()
                lines.append(f"Backup: {bkp}" if bkp else "Backup: failed")
            except Exception as e:
                lines.append(f"Backup error: {e}")
        if engine.agent_registry:
            try:
                hr = await engine.agent_registry.dispatch("hr")
                lines.append("HR audit: ok" if hr and hr.success else f"HR audit: fail ({getattr(hr, 'error', 'unknown')})")
            except Exception as e:
                lines.append(f"HR audit error: {e}")
            try:
                rs = await engine.agent_registry.dispatch("research", step=request or "agent improvements")
                lines.append("Research scan: ok" if rs and rs.success else f"Research scan: fail ({getattr(rs, 'error', 'unknown')})")
            except Exception as e:
                lines.append(f"Research scan error: {e}")
            try:
                si = await engine.agent_registry.dispatch("self_improve", step=request or "Improve weak agent interactions and safety")
                lines.append("Self-improve: ok" if si and si.success else f"Self-improve: fail ({getattr(si, 'error', 'unknown')})")
            except Exception as e:
                lines.append(f"Self-improve error: {e}")
        quality = await engine._maybe_quality_gate("documentation", request or "improvement_cycle", "\n".join(lines))
        return "Improvement cycle:\n- " + "\n- ".join(lines) + f"\n- Quality gate: {quality}"

    if action == "autonomous_execute":
        request = str(params.get("request") or "").strip()
        if not request:
            return "Пустой запрос."
        return await engine._autonomous_execute(request)

    if action == "register_account" and engine.agent_registry:
        url = params.get("url", "")
        form = params.get("form", {}) or {}
        submit_selector = params.get("submit_selector", "")
        code_selector = params.get("code_selector", "")
        code_submit_selector = params.get("code_submit_selector", "")
        if not url or not submit_selector:
            return "Нужны параметры: url и submit_selector"
        result = await engine.agent_registry.dispatch(
            "register_with_email",
            url=url,
            form=form,
            submit_selector=submit_selector,
            code_selector=code_selector,
            code_submit_selector=code_submit_selector,
            from_filter=params.get("from_filter", ""),
            subject_filter=params.get("subject_filter", ""),
            prefer_link=bool(params.get("prefer_link", False)),
            timeout_sec=int(params.get("timeout_sec", 180)),
            screenshot_path=params.get("screenshot_path", ""),
        )
        if result and result.success:
            return f"Регистрация выполнена: {str(result.output)[:200]}"
        return f"Регистрация не удалась: {getattr(result, 'error', 'unknown')}"

    if action == "run_kdp_draft_maintenance":
        target_title = str(params.get("target_title") or "").strip()
        language = str(params.get("language") or "English").strip() or "English"
        if not target_title:
            return "Для KDP-обновления нужен target_title."
        storage = str(getattr(settings, "KDP_STORAGE_STATE_FILE", "runtime/kdp_storage_state.json") or "runtime/kdp_storage_state.json")
        cmd = [
            "python3", "scripts/kdp_auth_helper.py", "fill-draft",
            "--storage-path", storage,
            "--headless",
            "--target-title", target_title,
            "--language", language,
        ]
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        out_b, _ = await asyncio.wait_for(proc.communicate(), timeout=180)
        out = (out_b or b"").decode("utf-8", errors="ignore")
        rc = int(proc.returncode or 0)
        if rc != 0:
            return f"KDP-драфт не обновлён (rc={rc}). {out[-600:]}"
        try:
            payload = json.loads(out.strip().splitlines()[-1])
        except Exception:
            payload = {}
        if isinstance(payload, dict):
            fields = payload.get("fields_filled") or []
            return (
                "KDP-драфт обновлён.\n"
                f"- title: {payload.get('target_title', target_title)}\n"
                f"- fields_filled: {', '.join(fields) if fields else 'none'}\n"
                f"- saved_clicked: {bool(payload.get('saved_clicked', False))}\n"
                f"- screenshot: {payload.get('debug_screenshot', '')}"
            )
        return f"KDP-драфт обработан. {out[-700:]}"

    if action == "run_platform_task":
        platform = str(params.get("platform") or "").strip().lower()
        request = str(params.get("request") or "").strip()
        low = request.lower()
        if not platform:
            return "Платформа не определена."
        create_like = any(k in low for k in ("опубликуй", "создай", "заполни", "редакт", "publish", "create", "draft", "черновик"))
        if (not create_like) and any(k in low for k in ("статус", "состояние", "есть ли", "проверь", "товар", "товары", "листинг")):
            if engine.agent_registry and platform in {"gumroad", "etsy", "kofi", "printful", "amazon_kdp"}:
                res = await engine.agent_registry.dispatch("sales_check", platform=platform)
                if res and res.success:
                    return f"{platform}: {str(res.output)[:1200]}"
        if platform == "amazon_kdp" and any(k in low for k in ("заполни", "редакт", "fill", "draft")):
            tt = engine._extract_target_title(request)
            if not tt:
                return "Для KDP редактирования укажи точное название драфта."
            return await engine._dispatch_action("run_kdp_draft_maintenance", {"target_title": tt, "language": "English"})
        if create_like or any(k in low for k in ("листинг", "товар")):
            recipe_map = {
                "gumroad": "gumroad_publish",
                "etsy": "etsy_publish",
                "kofi": "kofi_publish",
                "amazon_kdp": "kdp_publish",
                "twitter": "twitter_publish",
                "reddit": "reddit_publish",
                "pinterest": "pinterest_publish",
                "printful": "printful_publish",
            }
            recipe_name = recipe_map.get(platform)
            if recipe_name and engine.comms and hasattr(engine.comms, "_run_recipe_direct"):
                out = await engine.comms._run_recipe_direct(recipe_name, live=True, request_text=request)  # type: ignore[attr-defined]
                st = str(out.get("status") or "").strip().lower()
                if st == "accepted":
                    res = out.get("result") if isinstance(out.get("result"), dict) else {}
                    ev = res.get("evidence") if isinstance(res.get("evidence"), dict) else {}
                    status = str(res.get("status") or "").strip() or "-"
                    url = str(res.get("url") or ev.get("url") or "").strip() or "-"
                    rid = str(
                        res.get("listing_id") or res.get("product_id") or res.get("post_id") or res.get("tweet_id") or
                        res.get("document_id") or res.get("id") or ev.get("id") or "-"
                    ).strip()
                    return (
                        f"{platform}: задача выполнена через publish-flow.\n"
                        f"- status: {status}\n"
                        f"- url: {url}\n"
                        f"- id: {rid}"
                    )
                result = out.get("result") if isinstance(out.get("result"), dict) else {}
                return (
                    f"{platform}: publish-flow не прошёл.\n"
                    f"- причина: {out.get('error', 'unknown')}\n"
                    f"- status: {str(result.get('status') or '-')}"
                )
            topic = engine._extract_product_topic(request)
            return await engine._dispatch_action("run_product_pipeline", {"topic": topic, "platforms": [platform], "auto_publish": True})
        if platform in {"twitter", "reddit", "threads"} and engine.agent_registry:
            res = await engine.agent_registry.dispatch("social_media", platform=platform, content=request)
            if res and res.success:
                return f"{platform}: пост опубликован/принят. {str(res.output)[:500]}"
            return f"{platform}: не удалось выполнить постинг ({getattr(res, 'error', 'unknown')})."
        return f"{platform}: задача распознана, но для такого типа операции пока нет безопасного раннера."

    if action == "run_printful_etsy_sync":
        topic = str(params.get("topic") or "POD Listing").strip()
        auto_publish = bool(params.get("auto_publish", True))
        if not engine.agent_registry:
            return "AgentRegistry недоступен для Printful→Etsy."
        payload = {
            "sync_product": {"name": topic[:100] or "VITO POD Listing"},
            "sync_variants": [],
            "description": f"{topic} — generated by VITO test pipeline.",
            "dry_run": (not auto_publish),
        }
        create = await engine.agent_registry.dispatch("listing_create", platform="printful", data=payload)
        if not create or not create.success:
            return f"Printful: не удалось создать товар ({getattr(create, 'error', 'unknown')})."
        snap = await engine.agent_registry.dispatch("sales_check", platform="etsy")
        etsy_out = getattr(snap, "output", None) if snap and snap.success else None
        return (
            "Printful→Etsy: шаги выполнены.\n"
            f"- Printful create: ok\n"
            f"- Etsy snapshot: {str(etsy_out)[:700] if etsy_out is not None else 'not_available'}"
        )

    return ""
