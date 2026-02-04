"""
Date                    Author                          Change Details
02-02-2026              Debasish.P                      Find accurate locator


"""
from dataclasses import dataclass
from typing import List, Optional, Tuple

from playwright.sync_api import Page, Locator as PwLocator

from dataclass.conceptual_objects import Locator

# Strategy weights for confidence calculation (heuristic)
STRATEGY_WEIGHT = {
    "role": 1.0,
    "label": 0.95,
    "dataTestId": 0.9,
    "aria": 0.85,
    "text": 0.8,
    "placeholder": 0.75,
    "css": 0.6,
    "xpath": 0.45,
    "relative": 0.4,
}


@dataclass
class ResolvedLocator:
    primary: Locator
    alternates: List[Locator]
    confidence: float
    pw_locator: PwLocator  # Playwright locator to act upon


class LocatorResolver:
    """
    Resolves a Locator (and alternates) into a unique, visible Playwright locator.
    Computes a heuristic confidence score based on strategy and match quality.
    """

    def __init__(self, page: Page, priority: List[str], max_alts: int, locale: str = "en-IN"):
        self.page = page
        self.priority = priority
        self.max_alts = max_alts
        self.locale = locale

    def _to_pw(self, l: Locator) -> PwLocator:
        if l.strategy == "role":
            return self.page.get_by_role(l.role, name=l.name).nth(l.index)

        if l.strategy == "label":
            return self.page.get_by_label(l.value or l.name or "").nth(l.index)
        if l.strategy == "dataTestId":
            return self.page.get_by_test_id(l.value or "").nth(l.index)
        if l.strategy == "aria":
            if l.name:
                return self.page.get_by_role("button", name=l.name).nth(l.index)
            if l.value:
                return self.page.locator(f"[aria-label='{l.value}']").nth(l.index)
            return self.page.locator("[aria-label]").nth(l.index)
        if l.strategy == "text":
            return self.page.get_by_text(l.value or "", exact=True).nth(l.index)
        if l.strategy == "placeholder":
            return self.page.get_by_placeholder(l.value or "").nth(l.index)
        if l.strategy == "css":
            return self.page.locator(l.value or "").nth(l.index)
        if l.strategy == "xpath":
            return self.page.locator(f"xpath={l.value}").nth(l.index)
        if l.strategy == "relative":
            return self.page.get_by_text(l.value or "", exact=False).nth(l.index)
        return self.page.locator("html")

    def _visible_unique(self, pw_loc: PwLocator) -> Tuple[bool, int]:
        try:
            count = pw_loc.count()
            visible_count = 0
            for i in range(min(count, 10)):
                if pw_loc.nth(i).is_visible():
                    visible_count += 1
            return (visible_count == 1, visible_count)
        except Exception:
            return (False, 0)

    def _confidence(self, primary: Locator, visible_count: int) -> float:
        base = STRATEGY_WEIGHT.get(primary.strategy, 0.3)
        uniq_bonus = 0.25 if visible_count == 1 else 0.0
        return max(0.0, min(1.0, base + uniq_bonus))

    def resolve(self, candidates: List[Locator]) -> Optional[ResolvedLocator]:
        alternates: List[Locator] = []
        chosen: Optional[Locator] = None
        chosen_pw: Optional[PwLocator] = None
        conf = 0.0
        seen = 0

        for cand in candidates:
            pw = self._to_pw(cand)
            is_unique, visible_count = self._visible_unique(pw)
            if is_unique and chosen is None:
                chosen, chosen_pw = cand, pw
                conf = self._confidence(cand, visible_count)
            else:
                if seen < self.max_alts:
                    alternates.append(cand)
                    seen += 1

        if chosen and chosen_pw:
            return ResolvedLocator(primary=chosen, alternates=alternates, confidence=conf, pw_locator=chosen_pw)
        return None
