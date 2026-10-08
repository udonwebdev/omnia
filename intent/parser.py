import re
import time
import logging
from typing import Dict, Any, List, Tuple, Optional
from intent.models import UserIntent, AmbiguityDetail, AmbiguityState

logger = logging.getLogger("Omnia.Intent.Parser")

class IntentParser:
    """Parses natural-language user objectives, detects ambiguity, and normalizes entities."""

    def __init__(self):
        # Known target application keywords
        self.app_keywords = {
            "youtube": "YouTube",
            "chrome": "Google Chrome",
            "browser": "Browser",
            "settings": "Settings",
            "whatsapp": "WhatsApp",
            "terminal": "Terminal"
        }

        # Known dangerous verbs requiring confirmation
        self.destructive_verbs = ["delete", "remove", "drop", "wipe", "format", "purchase", "pay", "shutdown", "reboot"]

    def parse(self, raw_text: str, context: Optional[Dict[str, Any]] = None) -> UserIntent:
        """Parses a natural-language string into a strongly typed UserIntent."""
        raw_clean = raw_text.strip()
        normalized = re.sub(r"\s+", " ", raw_clean.lower())

        intent = UserIntent(
            raw_text=raw_clean,
            normalized_text=normalized,
            primary_objective=self._extract_primary_objective(normalized),
            entities={},
            parameters={},
            target_devices=[],
            target_applications=[],
            target_websites=[],
            temporal_constraints=[],
            safety_constraints=[]
        )

        # 1. Detect prompt injection attempts inside input text
        if self._detect_injection_attempt(raw_clean):
            logger.warning(f"PROMPT_INJECTION_FLAGGED: Untrusted override instruction detected in text: '{raw_clean[:40]}'")
            intent.safety_constraints.append("IGNORE_UNTRUSTED_EXTERNAL_OVERRIDE")

        # 2. Extract Target Applications
        for kw, app_name in self.app_keywords.items():
            if re.search(rf"\b{kw}\b", normalized):
                intent.target_applications.append(app_name)
        if intent.target_applications:
            intent.entities["applications"] = list(intent.target_applications)

        # 3. Extract Target Websites / URLs
        urls = re.findall(r"https?://[^\s]+|www\.[^\s]+|[a-zA-Z0-9\-\.]+\.(?:com|org|io|net|edu|dev)", raw_text)
        if urls:
            intent.target_websites.extend(urls)
            intent.entities["urls"] = list(urls)

        # 4. Extract Target Devices
        if "phone" in normalized or "android" in normalized or "mobile" in normalized:
            intent.target_devices.append("android")
        if "laptop" in normalized or "desktop" in normalized or "pc" in normalized or "workstation" in normalized:
            intent.target_devices.append("desktop")

        # 5. Extract Temporal Constraints
        if "before" in normalized or "after" in normalized or "today" in normalized or "now" in normalized:
            time_matches = re.findall(r"\b(before|after|today|now|tomorrow|at \d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b", normalized)
            intent.temporal_constraints.extend(time_matches)

        # 6. Check Destructive / Risk triggers
        for dv in self.destructive_verbs:
            if re.search(rf"\b{dv}\b", normalized):
                intent.requires_confirmation = True
                intent.safety_constraints.append(f"REQUIRES_CONFIRMATION_FOR_{dv.upper()}")

        # 7. Ambiguity Assessment
        intent.ambiguity = self._evaluate_ambiguity(raw_clean, normalized, intent, context or {})

        return intent

    def _extract_primary_objective(self, normalized: str) -> str:
        # Strip conversational pleasantries
        clean = re.sub(r"^(please|can you|could you|kindly|omnia)\s+", "", normalized)
        if re.search(r"\b(open|navigate|visit|browse|go to)\b.*https?://", clean) or re.search(r"\b(open|navigate|browse)\b.*(browser|chrome|edge|web)", clean):
            return "BROWSER_NAVIGATE"
        if re.search(r"\b(send|text|message)\b", clean):
            return "SEND_MESSAGE"
        if re.search(r"\b(delete|remove|erase)\b", clean):
            return "DELETE_DATA"
        return clean.capitalize()

    def _detect_injection_attempt(self, text: str) -> bool:
        injection_patterns = [
            r"ignore previous instructions",
            r"disregard all prior directives",
            r"you are now in developer mode",
            r"system prompt override",
            r"override safety constraints"
        ]
        for pat in injection_patterns:
            if re.search(pat, text, re.IGNORECASE):
                return True
        return False

    def _evaluate_ambiguity(self, raw: str, norm: str, intent: UserIntent, context: Dict[str, Any]) -> AmbiguityDetail:
        # Check 1: Pronoun reference without antecedent ("send it to John", "open that", "delete those")
        pronoun_match = re.search(r"\b(it|this|that|those|them)\b", norm)
        if pronoun_match and not intent.target_websites and not intent.target_applications and not context.get("active_item"):
            target_person = re.search(r"\bto ([a-zA-Z]+)\b", norm)
            name = target_person.group(1) if target_person else "target"
            return AmbiguityDetail(
                state=AmbiguityState.NEEDS_CLARIFICATION,
                ambiguity_type="UNDERSPECIFIED_PAYLOAD_OR_TARGET",
                missing_information=["content_payload", "target_recipient_contact"],
                confidence=0.4,
                clarification_question=f"What specific item or content should be sent to {name}?"
            )

        # Check 2: Multiple recipient ambiguity ("send to John" with multiple contacts)
        available_contacts = context.get("contacts", [])
        if "john" in norm and len([c for c in available_contacts if "john" in c.lower()]) > 1:
            return AmbiguityDetail(
                state=AmbiguityState.NEEDS_CLARIFICATION,
                ambiguity_type="AMBIGUOUS_RECIPIENT",
                missing_information=["contact_selection"],
                candidate_interpretations=[c for c in available_contacts if "john" in c.lower()],
                confidence=0.5,
                clarification_question="Multiple contacts named John found. Which one would you like to message?"
            )

        # Check 3: Underspecified high-risk action ("delete those files", "clean files")
        if ("delete" in norm or "remove" in norm) and not re.search(r"(file|dir|path|folder)\s+[\w\./\\]+", norm):
            return AmbiguityDetail(
                state=AmbiguityState.UNSAFE_TO_INFER,
                ambiguity_type="UNSPECIFIED_DELETION_TARGET",
                missing_information=["target_filepath"],
                confidence=0.2,
                clarification_question="Which specific file or directory do you want to delete?"
            )

        # Clean, unambiguous intent
        return AmbiguityDetail(
            state=AmbiguityState.CLEAR,
            confidence=0.95
        )

intent_parser = IntentParser()
