"""Acceso a datos de reglas de clasificación."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import ClassificationRule


class RuleRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, rule_id: int) -> ClassificationRule | None:
        return self.session.get(ClassificationRule, rule_id)

    def list_active(self) -> list[ClassificationRule]:
        return (
            self.session.query(ClassificationRule)
            .filter_by(active=True)
            .order_by(ClassificationRule.priority)
            .all()
        )

    def list_all(self) -> list[ClassificationRule]:
        return (
            self.session.query(ClassificationRule).order_by(ClassificationRule.priority).all()
        )

    def add(self, rule: ClassificationRule) -> ClassificationRule:
        self.session.add(rule)
        return rule
