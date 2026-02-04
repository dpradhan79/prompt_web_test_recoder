"""
Date                    Author                          Change Details
02-02-2026              Debasish.P                      Data Structure To Various Conceptual Work Items
"""
import json
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Literal, Dict, Any

ActionType = Literal[
    "navigate", "click", "fill", "press", "select", "check", "uncheck",
    "hover", "scroll", "waitFor", "assert_text", "assert_visible", "assert_match", "custom"
]

LocatorStrategyType = Literal[
    "role", "label", "dataTestId", "aria", "text", "placeholder", "css", "xpath", "relative"
]

WaitType = Literal["domReady", "load", "networkIdle"]


# ---------- Core dataclasses ----------

@dataclass
class WaitConfig:
    type: WaitType = "domReady"
    timeoutMs: int = 10000


@dataclass
class Locator:
    strategy: LocatorStrategyType
    role: Optional[str] = None
    name: Optional[str] = None  # used for role/aria accessible name
    value: Optional[str] = None  # used for text/placeholder/label/dataTestId/css/xpath/relative
    frame: Optional[str] = None  # frame hint (url/name/selector), null if main frame
    index: Optional[int] = 0  # index if more tha one locator found 0 based index, first element - 0 index


@dataclass
class Step:
    intent: str
    action: ActionType
    input: Optional[str]
    locator: Locator
    altLocators: List[Locator] = field(default_factory=list)
    wait: WaitConfig = field(default_factory=WaitConfig)
    reason: str = ""
    confidence: float = 0.0
    expectedText: Optional[str] = None
    pattern: Optional[str] = None
    domReference: int = 0
    screenReference: int = 0

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Normalize optional fields for strict JSON
        d["expectedText"] = self.expectedText if self.expectedText is not None else None
        d["pattern"] = self.pattern if self.pattern is not None else None
        return d


@dataclass
class ArtifactsMapEntry:
    id: int
    pathRef: str
    url: str
    timestamp: str
    domHash: Optional[str] = None


@dataclass
class ArtifactsMap:
    screenshots: List[ArtifactsMapEntry] = field(default_factory=list)
    dom: List[ArtifactsMapEntry] = field(default_factory=list)


@dataclass
class IntentItem:
    step_no: int
    intent: str


@dataclass
class Intents:
    intents: List[IntentItem]


# ---------- JSON utilities (drop-in) ----------

# Intents <-> JSON
def get_intents_from_json_str(json_str: str) -> Intents:
    raw = json.loads(json_str)
    return get_intents_from_dict(raw)


def get_intents_from_dict(raw: Dict[str, Any]) -> Intents:
    if "intents" not in raw or not isinstance(raw["intents"], list):
        raise ValueError("Invalid schema: missing 'intents' array.")
    items: List[IntentItem] = []
    for node in raw["intents"]:
        if not isinstance(node, dict) or "step" not in node or "intent" not in node:
            raise ValueError("Each intent requires 'step' (int) and 'intent' (str).")
        items.append(IntentItem(step_no=int(node["step"]), intent=str(node["intent"])))
    return Intents(intents=items)


def intents_to_json_dict(intents: Intents) -> Dict[str, Any]:
    return {"intents": [asdict(intent_item) for intent_item in intents.intents]}


def intents_to_json_str(intents: Intents, indent: int = 2) -> str:
    return json.dumps(intents_to_json_dict(intents), ensure_ascii=False, indent=indent)


# Steps <-> JSON
def step_from_json_obj(obj: Dict[str, Any]) -> Step:
    required = ["intent", "action", "locator", "wait", "confidence", "domReference", "screenReference"]
    for k in required:
        if k not in obj:
            raise ValueError(f"Step missing required field: {k}")

    locator = Locator(**obj["locator"])
    alt_locators = [Locator(**a) for a in obj.get("altLocators", [])]
    wait = WaitConfig(**obj["wait"])

    return Step(
        intent=str(obj["intent"]),
        action=str(obj["action"]),
        input=obj.get("input"),
        locator=locator,
        altLocators=alt_locators,
        wait=wait,
        reason=obj.get("reason", ""),
        confidence=float(obj.get("confidence", 0.0)),
        expectedText=obj.get("expectedText"),
        pattern=obj.get("pattern"),
        domReference=int(obj["domReference"]),
        screenReference=int(obj["screenReference"])
    )


def steps_from_json_str(json_str: str) -> List[Step]:
    raw = json.loads(json_str)
    if not isinstance(raw, list):
        raise ValueError("Steps JSON must be a list of step objects.")
    return [step_from_json_obj(o) for o in raw]


def steps_to_json(steps: List[Step], indent: int = 2) -> str:
    return json.dumps([s.to_dict() for s in steps], ensure_ascii=False, indent=indent)


# Artifacts <-> JSON
def artifacts_to_json_dict(art: ArtifactsMap) -> Dict[str, Any]:
    return {
        "screenshots": [asdict(e) for e in art.screenshots],
        "dom": [asdict(e) for e in art.dom],
    }


def artifacts_to_json_str(art: ArtifactsMap, indent: int = 2) -> str:
    return json.dumps(artifacts_to_json_dict(art), ensure_ascii=False, indent=indent)
