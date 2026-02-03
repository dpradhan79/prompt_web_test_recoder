"""
Date                Author                                  Change Details
02-02-2026          Debasish.P                              Managing Results/Generated Files
"""
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Tuple

from playwright.sync_api import Page

from conceptual_objects import ArtifactsMap, ArtifactsMapEntry


class ArtifactManager:
    def __init__(self, run_dir: Path, full_page: bool = False):
        self.run_dir = run_dir
        self.full_page = full_page
        self.dom_dir = self.run_dir / "dom"
        self.sc_dir = self.run_dir / "screens"
        self.dom_dir.mkdir(parents=True, exist_ok=True)
        self.sc_dir.mkdir(parents=True, exist_ok=True)
        self.screenshot_id = 0
        self.dom_id = 0
        self.map = ArtifactsMap()

    def _ts(self) -> str:
        return datetime.now().isoformat(timespec="seconds") + "Z"

    def _sha1(self, text: str) -> str:
        return "sha1:" + hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()

    def capture_dom_and_screenshot(self, page: Page) -> Tuple[int, int]:
        # DOM
        self.dom_id += 1
        dom_path = self.dom_dir / f"{self.dom_id:04d}.html"
        dom_content = page.content()
        dom_path.write_text(dom_content, encoding="utf-8")
        dom_entry = ArtifactsMapEntry(
            id=self.dom_id,
            pathRef=str(dom_path),
            url=page.url,
            timestamp=self._ts(),
            domHash=self._sha1(dom_content),
        )
        self.map.dom.append(dom_entry)

        # Screenshot
        self.screenshot_id += 1
        sc_path = self.sc_dir / f"{self.screenshot_id:04d}.png"
        page.screenshot(path=str(sc_path), full_page=self.full_page)
        sc_entry = ArtifactsMapEntry(
            id=self.screenshot_id,
            pathRef=str(sc_path),
            url=page.url,
            timestamp=self._ts(),
            domHash=None,
        )
        self.map.screenshots.append(sc_entry)

        return (self.dom_id, self.screenshot_id)

    def latest_ids(self) -> Tuple[int, int]:
        return (self.dom_id, self.screenshot_id)

    def to_dict(self) -> dict:
        return {
            "screenshots": [e.__dict__ for e in self.map.screenshots],
            "dom": [e.__dict__ for e in self.map.dom],
        }

    def get_dom_path_by_id(self, dom_id: int) -> str | None:
        for d in self.map.dom:
            if d.id == dom_id:
                return d.pathRef
        return None

    def get_screenshot_path_by_id(self, sc_id: int) -> str | None:
        for s in self.map.screenshots:
            if s.id == sc_id:
                return s.pathRef
        return None
