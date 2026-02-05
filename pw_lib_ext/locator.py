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
    ".*test.*": 1.0,
    "dataTestId": 0.95,
    "id": 0.9,
    "name": 0.95,
    "role": 0.8,
    "label": 0.75,
    "text": 0.70,
    "aria": 0.65,
    "placeholder": 0.6,
    "css": 0.5,
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
        if l.strategy == "id":
            return self.page.locator(f'{l.strategy}={l.name}').nth(l.index)
        if l.strategy == "name":
            return self.page.locator(f'[{l.strategy}={l.name}]').nth(l.index)
        if l.strategy == "class":
            return self.page.locator(f'[{l.strategy}*={l.name}]').nth(l.index)
        if l.strategy == "testHook":
            return self.page.locator(f'[{l.name}={l.value}]').nth(l.index)
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
        # uniq_bonus = 0.25 if visible_count == 1 else 0.0
        # return max(0.0, min(1.0, base + uniq_bonus))
        return base

    def resolve(self, locators: List[Locator]) -> Optional[ResolvedLocator]:
        alternateLocators: List[Locator] = []
        chosen_locator: Optional[Locator] = None
        chosen_pw_locator: Optional[PwLocator] = None
        conf = 0.0
        seen = 0

        for locator in locators:
            pw = self._to_pw(locator)
            is_unique, visible_count = self._visible_unique(pw)
            if is_unique and chosen_locator is None:
                chosen_locator, chosen_pw_locator = locator, pw
                conf = self._confidence(locator, visible_count)
            else:
                if seen < self.max_alts:
                    alternateLocators.append(locator)
                    seen += 1

        if chosen_locator and chosen_pw_locator:
            return ResolvedLocator(primary=chosen_locator, alternates=alternateLocators, confidence=conf, pw_locator=chosen_pw_locator)
        return None
