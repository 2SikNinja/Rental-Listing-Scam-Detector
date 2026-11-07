"""
Safety tips shown with every result.

Tips tied to a specific signal come first, so the advice matches what
was actually found. General tips always follow, because a low score is
never proof that a listing is safe.
"""

from app.scoring.engine import ScoredSignal

signalTips: dict[str, str] = {
    "RENT_FAR_BELOW_MARKET": "Compare the rent with similar listings nearby. A price this low is the most common bait in rental scams.",
    "RENT_BELOW_MARKET": "Compare the rent with similar listings nearby before committing.",
    "OWNER_UNAVAILABLE": "Insist on meeting the owner or their licensed property manager in person or on a live video call.",
    "CANNOT_SHOW_UNIT": "Do not rent a unit you cannot tour inside, in person or by live video with the landlord present.",
    "KEYS_MAILED": "A real landlord or manager will hand you the keys at move-in. Never pay for keys sent by mail.",
    "PAYMENT_BEFORE_VIEWING": "Do not pay any deposit, fee, or rent until you have seen the unit and signed a lease.",
    "UNTRACEABLE_PAYMENT": "Refuse wire transfers, gift cards, money transfer services, and crypto. That money is almost never recovered.",
    "PEER_TO_PEER_PAYMENT": "If you use an app like Zelle, only pay after signing a lease with a verified owner, since payments cannot be reversed.",
    "OFF_PLATFORM_CONTACT": "Keep conversations on the listing site, where fraud reporting and records are available.",
    "PERSONAL_INFO_REQUEST": "Share your Social Security number or bank details only on a formal application after you have toured the unit.",
    "PHOTO_REUSED_ELSEWHERE": "Run the photos through a reverse image search (Google Lens or TinEye) to see where else they appear.",
    "ADDRESS_LISTED_FOR_SALE": "Find the for-sale listing and call that listing agent directly to ask whether the home is really for rent.",
    "ADDRESS_RECENTLY_FOR_SALE": "Check county property records to confirm who owns the home now.",
    "ADDRESS_NOT_FOUND": "Look the address up on a map and street view to confirm the building exists.",
    "ADDRESS_ZIP_MISMATCH": "Confirm the exact address with the landlord and check it on a map.",
    "DISPOSABLE_EMAIL": "Ask for a way to reach the landlord that can be verified, such as a property management company's main office number.",
    "VOIP_PHONE_NUMBER": "Ask for an in-person or live video meeting, since an internet phone number alone doesn't confirm who you are talking to.",
    "CONTACT_REUSED_ELSEWHERE": "Search the phone number and email online to see what other listings or reports mention them.",
    "DESCRIPTION_REUSED_ELSEWHERE": "Search a sentence from the description online to find the original listing and compare the details.",
    "URGENCY_PRESSURE": "Take your time. Pressure to decide quickly is meant to stop you from checking details.",
}

generalTips = [
    "Search the address online to see whether it is listed for sale or by a different landlord.",
    "Check county property records to confirm the landlord's name matches the owner.",
    "Never send money before you have seen the unit in person or by live video and signed a lease.",
]


def buildSafetyTips(scoredSignals: list[ScoredSignal]) -> list[str]:
    tips: list[str] = []
    for scoredSignal in scoredSignals:
        tip = signalTips.get(scoredSignal.signal.signalCode)
        if tip and tip not in tips:
            tips.append(tip)
    for tip in generalTips:
        if tip not in tips:
            tips.append(tip)
    return tips
