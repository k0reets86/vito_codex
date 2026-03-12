from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes


async def cmd_recipe_run(agent, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Execute a workflow recipe through PublisherQueue with acceptance gate."""
    if await agent._reject_stranger(update):
        return
    if not agent._publisher_queue:
        await update.message.reply_text("PublisherQueue не подключён.", reply_markup=agent._main_keyboard())
        return
    args = list(getattr(context, "args", None) or [])
    if not args:
        await update.message.reply_text(
            "Использование: /recipe_run <recipe_name> [live]",
            reply_markup=agent._main_keyboard(),
        )
        return
    recipe_name = str(args[0] or "").strip().lower()
    live = any(str(a).strip().lower() == "live" for a in args[1:])
    try:
        out = await agent._run_recipe_direct(recipe_name, live=live)
    except Exception as e:
        await update.message.reply_text(f"Recipe run error: {e}", reply_markup=agent._main_keyboard())
        return

    platform = str(out.get("platform") or "-")
    st = str(out.get("status") or "")
    if st == "accepted":
        res = out.get("result") if isinstance(out.get("result"), dict) else {}
        status = str(res.get("status") or "")
        evidence = res.get("evidence") if isinstance(res.get("evidence"), dict) else {}
        url = str(res.get("url") or evidence.get("url") or "")
        rid = str(
            res.get("listing_id")
            or res.get("product_id")
            or res.get("document_id")
            or res.get("post_id")
            or res.get("tweet_id")
            or res.get("id")
            or evidence.get("id")
            or ""
        )
        await update.message.reply_text(
            f"Recipe accepted: {recipe_name} ({platform})\nstatus={status}\nurl={url or '-'}\nid={rid or '-'}",
            reply_markup=agent._main_keyboard(),
        )
        return

    result = out.get("result") if isinstance(out.get("result"), dict) else {}
    status = str(result.get("status") or "")
    await update.message.reply_text(
        f"Recipe failed: {recipe_name}\nПричина: {out.get('error', 'unknown')}\nstatus={status or '-'}",
        reply_markup=agent._main_keyboard(),
    )
