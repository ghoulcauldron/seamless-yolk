#!/usr/bin/env python3
"""
state_gate.py

Read-only helper for evaluating whether a given action is allowed
for a product based on capsule product_state.json.

This module:
- DOES NOT mutate state
- DOES NOT infer outcomes
- DOES NOT promote or demote products
- ONLY answers: "Is this action allowed right now?"

Schema version: STATE_SCHEMA v1.0
"""

from __future__ import annotations
import json
import pathlib
from dataclasses import dataclass
from typing import Optional, Dict


# --- Public API -------------------------------------------------------------

SUPPORTED_ACTIONS = {
    "include_in_import_csv",
    "image_upsert",
    "metafield_write",
    "collection_write",
}


@dataclass(frozen=True)
class GateDecision:
    allowed: bool
    reason: Optional[str]
    state_snapshot: Dict[str, Optional[str]]


class StateGate:
    """
    Read-only evaluator for product action permissions.
    """

    def __init__(self, state_file: str | pathlib.Path):
        self.state_path = pathlib.Path(state_file)
        if not self.state_path.exists():
            raise FileNotFoundError(f"State file not found: {self.state_path}")

        with open(self.state_path, "r") as f:
            self.state = json.load(f)

        self.products = self.state.get("products", {})
        self.schema_version = self.state.get("schema_version")

        if not self.products:
            raise ValueError("State file contains no products.")

    # --- Public method ------------------------------------------------------

    def can(
        self,
        *,
        handle: str,
        action: str,
    ) -> GateDecision:
        """
        Evaluate whether `action` is allowed for the product identified by `handle`.

        Parameters:
            handle (str): Shopify product handle
            action (str): One of SUPPORTED_ACTIONS

        Returns:
            GateDecision
        """

        # --- Validate inputs ------------------------------------------------

        if action not in SUPPORTED_ACTIONS:
            raise ValueError(
                f"Unsupported action '{action}'. "
                f"Supported actions: {sorted(SUPPORTED_ACTIONS)}"
            )

        product = self.products.get(handle)
        if not product:
            raise KeyError(f"Product handle not found in state: {handle}")

        allowed_actions = product.get("allowed_actions")
        if not isinstance(allowed_actions, dict):
            snapshot = {
                "current_stage": product.get("current_stage"),
                "preflight_status": product.get("preflight_status"),
                "image_state": product.get("image_state"),
            }
            return GateDecision(
                allowed=False,
                reason="allowed_actions_missing",
                state_snapshot=snapshot,
            )

        # --- Primary rule (authoritative) -----------------------------------

        allowed = bool(allowed_actions.get(action, False))

        # --- Snapshot for observability ------------------------------------

        snapshot = {
            "current_stage": product.get("current_stage"),
            "preflight_status": product.get("preflight_status"),
            "image_state": product.get("image_state"),
        }

        # --- Reason (explanatory only) --------------------------------------

        reason = None
        if not allowed:
            reason = self._derive_reason(product, action)

        return GateDecision(
            allowed=allowed,
            reason=reason,
            state_snapshot=snapshot,
        )

    # --- Internal helpers ---------------------------------------------------

    def _derive_reason(self, product: dict, action: str) -> str:
        """
        Derive a human-readable reason for denial.
        This is explanatory only and must not affect the decision.
        """

        preflight_status = product.get("preflight_status")
        image_state = product.get("image_state")
        ws_buy = product.get("ws_buy")

        if ws_buy:
            return "ws_buy=true"

        if preflight_status and preflight_status != "GO":
            return f"preflight_status={preflight_status}"

        if action == "image_upsert" and image_state:
            return f"image_state={image_state}"

        return f"allowed_actions.{action}=false"