from dataclasses import dataclass
from typing import Optional


@dataclass
class JurisdictionResult:
    forum: str
    threshold_rule: str


def consumer_forum_by_amount(claim_amount_inr: Optional[float]) -> JurisdictionResult:
    if claim_amount_inr is None:
        return JurisdictionResult(forum="Unknown", threshold_rule="missing_amount")

    if claim_amount_inr <= 5_000_000:
        return JurisdictionResult(
            forum="District Commission",
            threshold_rule="amount<=5000000",
        )
    if claim_amount_inr <= 20_000_000:
        return JurisdictionResult(
            forum="State Commission",
            threshold_rule="5000000<amount<=20000000",
        )
    return JurisdictionResult(
        forum="National Commission",
        threshold_rule="amount>20000000",
    )
