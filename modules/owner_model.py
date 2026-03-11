from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from config.logger import get_logger
from config.paths import PROJECT_ROOT
from modules.owner_preference_model import OwnerPreferenceModel

logger = get_logger("owner_model", agent="owner_model")

OWNER_MODEL_FILE = PROJECT_ROOT / "runtime" / "learnings" / "owner_model.json"


class OwnerModel:
    """Growing owner profile built on top of OwnerPreferenceModel + readable snapshot."""

    def __init__(self, sqlite_path: Optional[str] = None):
        self.pref = OwnerPreferenceModel(sqlite_path=sqlite_path)
        OWNER_MODEL_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not OWNER_MODEL_FILE.exists():
            OWNER_MODEL_FILE.write_text(json.dumps(self._default_model(), ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info("OwnerModel: инициализирован с defaults")

    def get_preferences(self) -> dict[str, Any]:
        model = self._load_file()
        explicit = self.pref.list_preferences(status="active", limit=200)
        model["explicit_preferences"] = [
            {"key": p.get("pref_key"), "value": p.get("value"), "confidence": p.get("confidence")}
            for p in explicit
        ]
        return model

    def update_from_decision(self, proposal: dict[str, Any], approved: bool) -> None:
        model = self._load_file()
        history = model.setdefault("decision_history", [])
        history.append(
            {
                "title": str(proposal.get("title") or ""),
                "type": str(proposal.get("type") or ""),
                "expected_revenue": proposal.get("expected_revenue"),
                "approved": bool(approved),
            }
        )
        history[:] = history[-100:]
        if approved:
            niche = str(proposal.get("title") or "").strip()
            if niche:
                liked = model.setdefault("approved_patterns", [])
                if niche not in liked:
                    liked.append(niche)
        self._save_file(model)

    def update_from_interaction(self, message: str, response: str = "") -> None:
        text = f"{message} {response}".lower()
        model = self._load_file()
        if any(tok in text for tok in ("осторож", "не публикуй", "черновик", "без списаний")):
            model["risk_appetite"] = "low"
            self.pref.set_preference("risk_appetite", {"level": "low"}, source="owner_model", confidence=0.85)
        if "на английском" in text:
            model["language"] = "en"
            self.pref.set_preference("output_language", {"value": "en"}, source="owner_model", confidence=0.95)
        self._save_file(model)

    def filter_goals(self, goals: list[dict[str, Any]]) -> list[dict[str, Any]]:
        model = self.get_preferences()
        risk = str(model.get("risk_appetite") or "medium").lower()
        filtered: list[dict[str, Any]] = []
        for goal in goals or []:
            effort = str(goal.get("effort") or "").lower()
            confidence = float(goal.get("confidence") or 0.0)
            if risk == "low" and effort == "high" and confidence < 0.8:
                continue
            if confidence < 0.35:
                continue
            filtered.append(goal)
        return filtered or list(goals or [])

    def _default_model(self) -> dict[str, Any]:
        return {
            "owner_name": "Vitalii",
            "risk_appetite": "low",
            "language": "en",
            "approved_patterns": [],
            "decision_history": [],
            "style": {"concise": True, "quality_first": True},
        }

    def _load_file(self) -> dict[str, Any]:
        try:
            return json.loads(OWNER_MODEL_FILE.read_text(encoding="utf-8"))
        except Exception:
            return self._default_model()

    def _save_file(self, payload: dict[str, Any]) -> None:
        OWNER_MODEL_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
