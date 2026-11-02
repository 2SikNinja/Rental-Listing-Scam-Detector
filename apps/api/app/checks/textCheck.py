"""
Text check: scans the listing title and description for wording that is
common in rental scams.

How it works:
  1. Normalize the text (lowercase, straight quotes, single spaces).
  2. Run each rule's regular expressions against it.
  3. Skip matches that are negated ("we never accept wire transfers"),
     so warnings written by honest landlords are not flagged.
  4. Return at most one signal per rule, with up to 3 matched phrases as
     evidence, so the user can see exactly what triggered it.

Why rules first: every flag is explainable and testable, which matters
more here than catching every possible phrasing. The known limit is
that scammers can reword things. An optional LLM pass (later step) can
catch rephrased versions, and near-duplicate description matching comes
once listings are stored in the database.
"""

from dataclasses import dataclass
import re

from app.checks.base import CheckOutcome, DetectedSignal
from app.schemas.listing import ListingSubmission, Severity

maxEvidenceItems = 3
maxEvidenceLength = 80

# A match is ignored if one of these words appears shortly before it,
# for example "no wire transfers" or "we will never ask for gift cards".
negationPattern = re.compile(
    r"\b(no|not|never|don'?t|do not|won'?t|will not|doesn'?t|does not|without|avoid|beware of)\b"
    r"(?:\W+\w+){0,4}\W*$"
)


@dataclass(frozen=True)
class TextRule:
    signalCode: str
    severity: Severity
    explanation: str
    patterns: tuple[re.Pattern[str], ...]
    allowNegation: bool = True


def compileAll(*rawPatterns: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(rawPattern) for rawPattern in rawPatterns)


textRules: tuple[TextRule, ...] = (
    TextRule(
        signalCode="OWNER_UNAVAILABLE",
        severity="high",
        explanation=(
            "The landlord says they are away (overseas, deployed, on a mission, or relocated). "
            "Scammers use this excuse to avoid meeting in person or showing the unit."
        ),
        patterns=compileAll(
            r"\b(i am|i'm|we are|we're|owner is|landlord is|currently)\s+(living\s+|working\s+|staying\s+)?"
            r"(overseas|abroad|out of the country|out of state|out of town)\b",
            r"\b(moved|relocated|transferred)\s+(overseas|abroad|out of the country|for (a |my )?(new )?job)\b",
            r"\b(missionary|mission trip|on a mission|deployed|military deployment|stationed (overseas|abroad))\b",
        ),
    ),
    TextRule(
        signalCode="CANNOT_SHOW_UNIT",
        severity="high",
        explanation=(
            "The listing says the unit cannot be shown, or only from the outside. Legitimate landlords "
            "almost always allow a viewing before you pay."
        ),
        patterns=compileAll(
            r"\b(can'?t|cannot|can not|unable to|won'?t be able to|not able to)\s+(show|view|see|tour)\b",
            r"\bno\s+(viewings?|showings?|tours?|walk-?throughs?)\b",
            r"\b(drive by|look from (the )?outside|view from (the )?outside)\b",
            r"\bdo(n'?t| not) disturb the (current )?(tenants?|occupants?)\b",
        ),
        allowNegation=False,
    ),
    TextRule(
        signalCode="KEYS_MAILED",
        severity="high",
        explanation=(
            "The listing offers to mail or ship the keys. This lets a scammer collect payment for a "
            "unit they do not control and never meet you."
        ),
        patterns=compileAll(
            r"\bkeys?\s+(will be|would be|can be|to be|are|is)?\s*(mailed|shipped|sent|couriered|posted|delivered)\b",
            r"\b(mail|ship|send|courier|post|deliver)\s+(you\s+)?(the\s+)?keys?\b",
        ),
    ),
    TextRule(
        signalCode="PAYMENT_BEFORE_VIEWING",
        severity="high",
        explanation=(
            "The listing asks for money (deposit, first month, or a holding fee) before you see the unit. "
            "Never pay before viewing in person or by live video."
        ),
        patterns=compileAll(
            r"\b(deposit|payment|first month|holding fee|reservation fee)\b[^.!?\n]{0,60}"
            r"\bbefore\s+(viewing|seeing|showing|touring|the viewing|a viewing|you see|you view|move-?in)\b",
            r"\b(send|pay|wire|transfer)\b[^.!?\n]{0,40}\b(deposit|payment|fee|first month)\b[^.!?\n]{0,40}"
            r"\bto\s+(hold|reserve|secure|lock in)\b",
            r"\b(holding|reservation)\s+(fee|deposit)\b",
        ),
    ),
    TextRule(
        signalCode="UNTRACEABLE_PAYMENT",
        severity="high",
        explanation=(
            "The listing asks for payment by wire transfer, gift cards, money transfer services, or "
            "cryptocurrency. This money is very hard to trace or get back."
        ),
        patterns=compileAll(
            r"\bwire(d)?\s+(transfer|the money|the deposit|payment|funds)\b",
            r"\b(western union|moneygram|money gram|gift ?cards?|itunes cards?|google play cards?|steam cards?)\b",
            r"\b(bitcoin|btc|crypto(currency)?|usdt|tether|ethereum)\b",
            r"\bpaypal\s+(friends|f&f)\b",
        ),
    ),
    TextRule(
        signalCode="PEER_TO_PEER_PAYMENT",
        severity="medium",
        explanation=(
            "The listing asks for payment through an instant app like Zelle, Venmo, or Cash App. Some real "
            "landlords use these, but payments usually cannot be reversed, so scammers prefer them."
        ),
        patterns=compileAll(r"\b(zelle|venmo|cash ?app|cashapp|apple cash)\b"),
    ),
    TextRule(
        signalCode="OFF_PLATFORM_CONTACT",
        severity="medium",
        explanation=(
            "The listing pushes you to contact the landlord outside the listing site (personal email, "
            "text, WhatsApp, Telegram). This avoids the site's fraud protections."
        ),
        patterns=compileAll(
            r"\b(whatsapp|telegram|signal app|wechat|google voice)\b",
            r"\b(text|email|e-mail|contact|reach)\s+me\s+(only\s+)?(directly|privately|at|on|via)\b",
            r"\b(only|just)\s+(contact|reach|text|email)\s+(me\s+)?(by|via|through|on)\b",
        ),
        allowNegation=False,
    ),
    TextRule(
        signalCode="PERSONAL_INFO_REQUEST",
        severity="medium",
        explanation=(
            "The listing asks for sensitive personal information (like a Social Security number or bank "
            "details) up front. Share these only through a formal application after viewing."
        ),
        patterns=compileAll(
            r"\b(social security|ssn|bank account (number|details|info)|routing number|copy of (your )?(id|passport|license))\b",
        ),
    ),
    TextRule(
        signalCode="URGENCY_PRESSURE",
        severity="low",
        explanation=(
            "The listing pressures you to act quickly. Urgency is a common tactic to stop people from "
            "checking details before paying."
        ),
        patterns=compileAll(
            r"\b(act fast|act now|won'?t last|first come,? first serve(d)?|many (other )?(people|applicants) (are )?interested)\b",
            r"\b(today only|must decide (today|now)|hurry|urgent(ly)?)\b",
        ),
    ),
)


def normalizeText(rawText: str) -> str:
    """Lowercase, straighten curly quotes, and collapse whitespace."""
    straightened = (
        rawText.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    )
    return re.sub(r"\s+", " ", straightened.lower()).strip()


def isNegated(normalizedText: str, matchStart: int) -> bool:
    """True if a negation word appears in the few words before the match."""
    precedingText = normalizedText[max(0, matchStart - 40):matchStart]
    sentenceStart = max(precedingText.rfind("."), precedingText.rfind("!"), precedingText.rfind("?"))
    if sentenceStart != -1:
        precedingText = precedingText[sentenceStart + 1:]
    return negationPattern.search(precedingText) is not None


def findRuleMatches(rule: TextRule, normalizedText: str) -> list[str]:
    matchedPhrases: list[str] = []
    for pattern in rule.patterns:
        for match in pattern.finditer(normalizedText):
            if rule.allowNegation and isNegated(normalizedText, match.start()):
                continue
            phrase = match.group(0)[:maxEvidenceLength]
            if phrase not in matchedPhrases:
                matchedPhrases.append(phrase)
            if len(matchedPhrases) >= maxEvidenceItems:
                return matchedPhrases
    return matchedPhrases


def runTextCheck(submission: ListingSubmission) -> CheckOutcome:
    combinedText = normalizeText(f"{submission.title or ''}. {submission.description}")

    detectedSignals: list[DetectedSignal] = []
    for rule in textRules:
        matchedPhrases = findRuleMatches(rule, combinedText)
        if matchedPhrases:
            detectedSignals.append(
                DetectedSignal(
                    checkName="text",
                    signalCode=rule.signalCode,
                    severity=rule.severity,
                    explanation=rule.explanation,
                    evidence={"matchedPhrases": matchedPhrases},
                )
            )

    return CheckOutcome(checkName="text", ran=True, signals=detectedSignals)
