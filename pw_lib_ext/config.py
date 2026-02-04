"""
Date                    Author                          Change Details
02-02-2026              Debasish.P                      Data Structure For Configuration
"""
from dataclasses import dataclass, field
from typing import Literal, Dict, Any

WaitType = Literal["domReady", "load", "networkIdle"]


@dataclass
class BrowserConfig:
    engine: Literal["chromium", "firefox", "webkit"] = "chromium"
    headless: bool = False
    slowMoMs: int = 0
    viewport: Dict[str, int] = field(default_factory=lambda: {"width": 1366, "height": 768})
    locale: str = "en-IN"
    timezoneId: str = "Asia/Kolkata"
    recordVideo: bool = False


@dataclass
class WaitDefaults:
    navigate: Dict[str, Any] = field(default_factory=lambda: {"type": "domReady", "timeoutMs": 10000})
    interaction: Dict[str, Any] = field(default_factory=lambda: {"type": "domReady", "timeoutMs": 10000})


@dataclass
class ArtifactPolicy:
    captureOnUrlChange: bool = True
    captureOnAutoSuggestVisible: bool = True
    captureOnEveryStep: bool = False
    fullPageScreenshots: bool = False


@dataclass
class RetryPolicy:
    maxRetriesPerStep: int = 2
    scrollProbe: bool = True
    handleCookieBanners: bool = True


@dataclass
class SelfHealing:
    enableSemanticBias: bool = True
    preferA11y: bool = True
    preferStableText: bool = True


@dataclass
class GroundingConfig:
    locatorPriority: list[str] = field(default_factory=lambda: [
        "role", "label", "dataTestId", "aria", "text", "placeholder", "css", "xpath", "relative"
    ])
    maxAltLocatorsPerStep: int = 3
    minConfidenceToRequireAlt: float = 0.85
    assertionMode: Literal["exact", "regex"] = "regex"
    assertionAlsoCheckVisible: bool = True
    artifactPolicy: ArtifactPolicy = field(default_factory=ArtifactPolicy)
    waitDefaults: WaitDefaults = field(default_factory=WaitDefaults)
    retryPolicy: RetryPolicy = field(default_factory=RetryPolicy)
    selfHealing: SelfHealing = field(default_factory=SelfHealing)


@dataclass
class LoggingConfig:
    verbosity: Literal["silent", "normal", "verbose"] = "verbose"
    saveRunLog: bool = True


@dataclass
class AppConfig:
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    grounding: GroundingConfig = field(default_factory=GroundingConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
