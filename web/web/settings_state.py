"""Reflex state for the Settings tab — user profile, config, sources,
disqualifiers, and target roles. All actions go through the shared harness_db
libraries (the same code path the TUI uses), so both front-ends stay in sync.
"""

from __future__ import annotations

import dataclasses

import reflex as rx
from harness_db import config_store, disqualifiers, sources_store, target_roles, users
from harness_db.config import get_active_uid, set_active_uid
from harness_db.disqualifiers import PREFILTER_CATEGORIES
from harness_db.seed import ensure_schema_and_seed
from harness_db.target_roles import KINDS

from web.data import engine as _shared_engine


@dataclasses.dataclass
class UserRowVM:
    uid: str
    active: bool
    is_current: bool


@dataclasses.dataclass
class ConfigRowVM:
    key: str
    value: str


@dataclasses.dataclass
class SourceRowVM:
    source_id: str
    description: str
    enabled: bool


@dataclasses.dataclass
class RuleRowVM:
    id: int
    label: str
    sublabel: str
    enabled: bool
    custom: bool


class SettingsState(rx.State):
    active_uid: str = ""
    message: str = ""

    users: list[UserRowVM] = []
    configs: list[ConfigRowVM] = []
    config_edits: dict[str, str] = {}
    sources: list[SourceRowVM] = []
    prefilters: list[RuleRowVM] = []
    scorings: list[RuleRowVM] = []
    roles: list[RuleRowVM] = []

    # Form inputs.
    new_user: str = ""
    new_prefilter_category: str = PREFILTER_CATEGORIES[0]
    new_prefilter_value: str = ""
    new_role_kind: str = KINDS[0]
    new_role_value: str = ""

    prefilter_categories: list[str] = list(PREFILTER_CATEGORIES)
    role_kinds: list[str] = list(KINDS)

    # --- loading -------------------------------------------------------------

    def load(self):
        ensure_schema_and_seed()
        self._reload()

    def _engine(self):
        # Reuse the process-wide cached engine (web.data.engine is lru_cached)
        # so each event doesn't rebuild the connection pool.
        return _shared_engine()

    def _reload(self):
        self.active_uid = get_active_uid()
        uid = self.active_uid
        self.users = [
            UserRowVM(uid=u.uid, active=bool(u.active), is_current=(u.uid == uid))
            for u in users.list_users(self._engine())
        ]
        cfg = config_store.list_config(uid)
        self.configs = [ConfigRowVM(key=k, value=v or "") for k, v in cfg.items()]
        self.config_edits = {k: (v or "") for k, v in cfg.items()}
        self.sources = [
            SourceRowVM(source_id=s.source_id, description=s.description, enabled=s.enabled)
            for s in sources_store.list_sources(uid)
        ]
        self.prefilters = [
            RuleRowVM(
                id=r.id, label=r.value, sublabel=r.category, enabled=r.enabled, custom=r.custom
            )
            for r in disqualifiers.list_prefilter_rules(uid)
        ]
        self.scorings = [
            RuleRowVM(
                id=b.id,
                label=b.name,
                sublabel=f"{b.modifier:+d}",
                enabled=b.enabled,
                custom=b.custom,
            )
            for b in disqualifiers.list_scoring_blocks(uid)
        ]
        self.roles = [
            RuleRowVM(id=i.id, label=i.value, sublabel=i.kind, enabled=i.enabled, custom=i.custom)
            for i in target_roles.list_target_roles(uid)
        ]

    # --- form setters --------------------------------------------------------

    def set_new_user(self, value: str):
        self.new_user = value

    def set_new_prefilter_category(self, value: str):
        self.new_prefilter_category = value

    def set_new_prefilter_value(self, value: str):
        self.new_prefilter_value = value

    def set_new_role_kind(self, value: str):
        self.new_role_kind = value

    def set_new_role_value(self, value: str):
        self.new_role_value = value

    # --- profile -------------------------------------------------------------

    def add_user(self):
        uid = self.new_user.strip()
        if not uid:
            return
        try:
            users.create_user(self._engine(), uid)
        except ValueError as e:
            self.message = str(e)
            return
        self.new_user = ""
        self.message = f"Created user {uid}"
        self._reload()

    def use_user(self, uid: str):
        set_active_uid(uid)
        self.message = f"Active user is now {uid}"
        self._reload()

    def toggle_user_active(self, uid: str):
        current = next((u.active for u in self.users if u.uid == uid), True)
        users.set_active(self._engine(), uid, not current)
        self._reload()

    # --- config --------------------------------------------------------------

    def set_config_edit(self, key: str, value: str):
        # Reassign (not in-place mutate) so Reflex reliably tracks the change.
        self.config_edits = {**self.config_edits, key: value}

    def save_config(self):
        for key, value in self.config_edits.items():
            config_store.set_config(key, value.strip(), self.active_uid)
        self.message = "Config saved"
        self._reload()

    # --- sources -------------------------------------------------------------

    def set_source(self, source_id: str, enabled: bool):
        sources_store.set_enabled(source_id, enabled, self.active_uid)
        self._reload()

    # --- disqualifiers -------------------------------------------------------

    def set_prefilter(self, rule_id: int, enabled: bool):
        disqualifiers.set_prefilter_enabled(rule_id, enabled, self.active_uid)
        self._reload()

    def add_prefilter(self):
        value = self.new_prefilter_value.strip()
        if not value:
            return
        disqualifiers.add_prefilter_rule(self.new_prefilter_category, value, self.active_uid)
        self.new_prefilter_value = ""
        self._reload()

    def delete_prefilter(self, rule_id: int):
        try:
            disqualifiers.delete_prefilter_rule(rule_id, self.active_uid)
        except ValueError as e:
            self.message = str(e)
            return
        self._reload()

    def set_scoring(self, block_id: int, enabled: bool):
        disqualifiers.set_scoring_enabled(block_id, enabled, self.active_uid)
        self._reload()

    # --- target roles --------------------------------------------------------

    def set_role(self, item_id: int, enabled: bool):
        target_roles.set_enabled(item_id, enabled, self.active_uid)
        self._reload()

    def add_role(self):
        value = self.new_role_value.strip()
        if not value:
            return
        target_roles.add_target_role(self.new_role_kind, value, self.active_uid)
        self.new_role_value = ""
        self._reload()

    def delete_role(self, item_id: int):
        try:
            target_roles.delete_target_role(item_id, self.active_uid)
        except ValueError as e:
            self.message = str(e)
            return
        self._reload()
