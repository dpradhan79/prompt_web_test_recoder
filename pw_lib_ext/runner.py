"""
Date                    Author                          Change Details
02-02-2026              Coforge                      Step Executor

"""
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright, Playwright, Browser, BrowserContext, Page, expect

from artifacts.artifacts import ArtifactManager
from dataclass.conceptual_objects import Step, WaitConfig, artifacts_to_json_dict, steps_to_json
from pw_lib_ext.config import AppConfig
from pw_lib_ext.locator import LocatorResolver

NAV_WAIT_MAP = {
    "domReady": "domcontentloaded",
    "load": "load",
    "networkIdle": "networkidle",
}


class PWStepExecutor:
    def __init__(self, cfg: AppConfig, run_dir: Path):
        self.cfg = cfg
        self.run_dir = run_dir
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts = ArtifactManager(run_dir, full_page=cfg.grounding.artifactPolicy.fullPageScreenshots)
        self._pw: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._ctx: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self.run_log: Dict[str, Any] = {
            "meta": {
                "startedAt": datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(timespec="seconds") + "Z",
                "browser": cfg.browser.__dict__,
                "locale": cfg.browser.locale,
            },
            "steps": [],
        }

    # ---------- lifecycle ----------
    def start(self):
        self._pw = sync_playwright().start()
        engine = self.cfg.browser.engine
        headless = self.cfg.browser.headless
        slow_mo = self.cfg.browser.slowMoMs

        if engine == "chromium":
            self._browser = self._pw.chromium.launch(headless=headless, slow_mo=slow_mo)
        elif engine == "firefox":
            self._browser = self._pw.firefox.launch(headless=headless, slow_mo=slow_mo)
        elif engine == "webkit":
            self._browser = self._pw.webkit.launch(headless=headless, slow_mo=slow_mo)
        else:
            self._browser = self._pw.chromium.launch(headless=headless, slow_mo=slow_mo)

        self._ctx = self._browser.new_context(
            locale=self.cfg.browser.locale,
            timezone_id=self.cfg.browser.timezoneId,
            viewport=self.cfg.browser.viewport,
            record_video_dir=str(self.run_dir / "videos") if self.cfg.browser.recordVideo else None
        )
        self._page = self._ctx.new_page()

    def close(self):
        self.run_log["endedAt"] = datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(timespec="seconds") + "Z"
        if self._page: self._page.close()
        if self._ctx: self._ctx.close()
        if self._browser: self._browser.close()
        if self._pw: self._pw.stop()

    # ---------- utilities ----------
    def _log_step(self, entry: Dict[str, Any]):
        if self.cfg.logging.verbosity == "verbose":
            notes_found: str = entry.get("status")

            if "passed" in notes_found.lower():  # Passed
                print(f"[STEP - {entry.get('index')}] {entry.get('intent')} -> {entry.get('status')}")
            else:
                # failed
                print(
                    f"[STEP - {entry.get('index')}] {entry.get('intent')} -> {entry.get('status')} -> {entry.get('notes')}")

        self.run_log["steps"].append(entry)

    def _save_json(self, obj: Any, path: Path):
        path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")

    def _capture_artifacts_if_needed(self, prev_url: str, autosuggest_visible: bool = False) -> Tuple[int, int]:
        assert self._page
        need = False
        if self.cfg.grounding.artifactPolicy.captureOnUrlChange and (self._page.url != prev_url):
            need = True
        if (self.cfg.grounding.artifactPolicy.captureOnAutoSuggestVisible and autosuggest_visible):
            need = True
        if self.cfg.grounding.artifactPolicy.captureOnEveryStep:
            need = True
        if need:
            return self.artifacts.capture_dom_and_screenshot(self._page)
        return self.artifacts.latest_ids()

    def _apply_wait(self, kind: str, wait_cfg: WaitConfig):
        assert self._page
        if kind == "navigate":
            self._page.wait_for_load_state(NAV_WAIT_MAP.get(wait_cfg.type, "domcontentloaded"),
                                           timeout=wait_cfg.timeoutMs)

    def _autosuggest_appeared(self) -> bool:
        assert self._page
        try:
            lb = self._page.get_by_role("listbox")
            if lb and lb.count() > 0 and lb.first.is_visible():
                return True
            opt = self._page.get_by_role("option")
            if opt and opt.count() > 0 and opt.first.is_visible():
                return True
        except Exception:
            return False
        return False

    # ---------- main execution ----------
    def execute_steps(self, steps: List[Step], step_no: int = 1) -> List[Step]:
        assert self._page
        final_steps: List[Step] = []
        # dom_id, sc_id = self.artifacts.capture_dom_and_screenshot(self._page)

        for idx, step in enumerate(steps, start=1):
            url_before = self._page.url
            log_entry: Dict[str, Any] = {
                "index": step_no, "intent": step.intent, "action": step.action,
                "urlBefore": url_before, "urlAfter": None,
                "locatorTried": [], "chosenLocator": None,
                "altLocatorsUsed": False, "confidence": step.confidence,
                "wait": step.wait.__dict__, "artifacts": {}, "timingsMs": {}, "status": "pending", "notes": ""
            }

            try:
                resolver = LocatorResolver(
                    page=self._page,
                    priority=self.cfg.grounding.locatorPriority,
                    max_alts=self.cfg.grounding.maxAltLocatorsPerStep,
                    locale=self.cfg.browser.locale,
                )

                # navigate
                if step.action == "navigate":
                    if not step.input:
                        raise ValueError("Navigate action requires 'input' URL.")
                    self._page.goto(step.input, wait_until=NAV_WAIT_MAP.get(step.wait.type, "domcontentloaded"),
                                    timeout=step.wait.timeoutMs)
                    dom_id, sc_id = self._capture_artifacts_if_needed(url_before)
                    step.domReference, step.screenReference = dom_id, sc_id
                    log_entry["status"] = "passed"
                    log_entry["urlAfter"] = self._page.url
                    log_entry["artifacts"] = {"domReference": dom_id, "screenReference": sc_id}
                    final_steps.append(step)
                    self._log_step(log_entry)
                    continue

                # Resolve candidates
                candidates = [step.locator] + step.altLocators
                for c in candidates:
                    log_entry["locatorTried"].append(c.__dict__)

                resolved = resolver.resolve(candidates)
                if not resolved:
                    raise RuntimeError("Unable to resolve a unique visible locator.")

                pw_loc = resolved.pw_locator
                # LLM Based confidence is used, Locator based weightage is not used
                # step.confidence = resolved.confidence
                step.altLocators = resolved.alternates

                # Execute
                if not self.cfg.browser.headless:
                    # pw_loc.scroll_into_view_if_needed()
                    pw_loc.highlight()

                if step.action == "click":
                    pw_loc.click(timeout=step.wait.timeoutMs)
                elif step.action == "press_sequentially":
                    if step.input is None:
                        raise ValueError("Press_sequentially action requires 'input'.")
                    pw_loc.click(timeout=step.wait.timeoutMs)
                    pw_loc.press_sequentially(step.input, delay=80, timeout=step.wait.timeoutMs)
                elif step.action == "fill":
                    if step.input is None:
                        raise ValueError("Fill action requires 'input'.")
                    pw_loc.click(timeout=step.wait.timeoutMs)
                    # pw_loc.fill(step.input, timeout=step.wait.timeoutMs)
                    pw_loc.press_sequentially(step.input, delay=80, timeout=step.wait.timeoutMs)
                    time.sleep(5)
                elif step.action == "press":
                    if step.input is None:
                        raise ValueError("Press action requires 'input' (key).")
                    pw_loc.press(step.input, timeout=step.wait.timeoutMs)
                elif step.action == "select":
                    pw_loc.click(timeout=step.wait.timeoutMs)
                elif step.action == "check":
                    pw_loc.check(timeout=step.wait.timeoutMs)
                elif step.action == "uncheck":
                    pw_loc.uncheck(timeout=step.wait.timeoutMs)
                elif step.action == "hover":
                    pw_loc.hover(timeout=step.wait.timeoutMs)
                elif step.action == "scroll":
                    self._page.evaluate("el => el.scrollIntoView({block: 'center', behavior: 'instant'})", pw_loc)
                elif step.action == "waitFor":
                    pw_loc.wait_for(state="visible", timeout=step.wait.timeoutMs)
                elif step.action == "assert_visible":
                    expect(pw_loc).to_be_visible(timeout=step.wait.timeoutMs)
                elif step.action == "assert_text":
                    if step.expectedText is None:
                        raise ValueError("assert_text requires 'expectedText'.")
                    expect(pw_loc).to_have_text(step.expectedText, timeout=step.wait.timeoutMs)
                    if self.cfg.grounding.assertionAlsoCheckVisible:
                        expect(pw_loc).to_be_visible(timeout=step.wait.timeoutMs)
                elif step.action == "assert_match":
                    if step.pattern is None:
                        raise ValueError("assert_match requires 'pattern'.")
                    pattern = step.pattern
                    flags = 0
                    if pattern.startswith("/") and pattern.endswith("/i"):
                        core = pattern[1:-2]
                        flags = re.I
                    elif pattern.startswith("/") and pattern.endswith("/"):
                        core = pattern[1:-1]
                    else:
                        core = pattern
                    regex = re.compile(core, flags)
                    expect(pw_loc).to_have_text(regex, timeout=step.wait.timeoutMs)
                    if self.cfg.grounding.assertionAlsoCheckVisible:
                        expect(pw_loc).to_be_visible(timeout=step.wait.timeoutMs)
                elif step.action == "assert_title":
                    if step.input is not None:
                        expect(self._page).to_have_title(step.input)
                    else:
                        raise ValueError('Input Is Not Provided')
                elif step.action == "custom":
                    raise NotImplementedError(f"Unsupported action: {step.action}")
                else:
                    raise NotImplementedError(f"Unsupported action: {step.action}")

                # Artifacts on autosuggest and URL change
                autosuggest_flag = False
                if self.cfg.grounding.artifactPolicy.captureOnAutoSuggestVisible:
                    autosuggest_flag = self._autosuggest_appeared()  # if listbox or option are present which are event driven loaded

                self._page.wait_for_load_state()
                self._page.wait_for_load_state("domcontentloaded")
                try:  # networkidle may throw error, its discouraged in documentation
                    self._page.wait_for_load_state("networkidle")
                except Exception:
                    pass

                time.sleep(2)  # give some extra time for page to settle down
                # if configuration set for artifacts (DOM/Screenshot) to be captured, it will be captured
                dom_id, sc_id = self._capture_artifacts_if_needed(url_before, autosuggest_visible=autosuggest_flag)
                step.domReference, step.screenReference = dom_id, sc_id

                # Log
                log_entry["chosenLocator"] = step.locator.__dict__
                log_entry["altLocatorsUsed"] = len(step.altLocators) > 0
                log_entry["confidence"] = step.confidence
                log_entry["status"] = "passed"
                log_entry["urlAfter"] = self._page.url
                log_entry["artifacts"] = {"domReference": dom_id, "screenReference": sc_id}

                final_steps.append(step)
                self._log_step(log_entry)

            except Exception as e:
                log_entry["status"] = "failed"
                log_entry["notes"] = str(e)
                log_entry["urlAfter"] = self._page.url
                self._log_step(log_entry)
                final_steps.append(step)

        return final_steps

    # ---------- save outputs ----------
    def save_outputs(self, steps: List[Step], plan_file: str = "plan.json", artifacts_file: str = "artifacts.json",
                     run_log_file: str = "run_log.json"):
        plan_path = self.run_dir / plan_file
        artifacts_path = self.run_dir / artifacts_file
        runlog_path = self.run_dir / run_log_file

        plan_json = steps_to_json(steps)
        plan_path.write_text(plan_json, encoding="utf-8")

        artifacts_json = artifacts_to_json_dict(self.artifacts.map)
        self._save_json(artifacts_json, artifacts_path)

        if self.cfg.logging.saveRunLog:
            self._save_json(self.run_log, runlog_path)
