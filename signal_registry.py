from typing import Dict, List, Optional
from pydantic import BaseModel

class SignalOption(BaseModel):
    label: str
    refined_tag: str

class SignalDefinition(BaseModel):
    signal_name: str
    question: str
    options: List[SignalOption]

SIGNAL_REGISTRY: Dict[str, List[SignalDefinition]] = {
    "money_not_paid": [
        SignalDefinition(
            signal_name="payment_type",
            question="What kind of payment was not given?",
            options=[
                SignalOption(label="Monthly salary", refined_tag="under_payment"),
                SignalOption(label="Final settlement after leaving job", refined_tag="gratuity_dispute"),
                SignalOption(label="Retirement benefit", refined_tag="pf_dispute"),
                SignalOption(label="Performance Bonus", refined_tag="bonus_not_paid"),
                SignalOption(label="Something else", refined_tag="money_not_paid")
            ]
        )
    ],
    "gratuity_dispute": [
        SignalDefinition(
            signal_name="employment_end",
            question="Did you complete 5 years of service before leaving?",
            options=[
                SignalOption(label="Yes, more than 5 years", refined_tag="gratuity_dispute"),
                SignalOption(label="No, less than 5 years", refined_tag="money_not_paid"),
                SignalOption(label="I am still working there", refined_tag="money_not_paid")
            ]
        )
    ],
    "pf_dispute": [
        SignalDefinition(
            signal_name="employer_contribution",
            question="Is the issue about missing contributions or withdrawal?",
            options=[
                SignalOption(label="Employer did not contribute", refined_tag="pf_not_contributed"),
                SignalOption(label="Withdrawal being stopped", refined_tag="pf_dispute"),
                SignalOption(label="I don't have a UAN number", refined_tag="pf_dispute")
            ]
        )
    ],
    "unauthorized_access": [
        SignalDefinition(
            signal_name="access_type",
            question="How was the access gained?",
            options=[
                SignalOption(label="Hacked through a link", refined_tag="unauthorized_access"),
                SignalOption(label="Phishing / OTP fraud", refined_tag="fraud_signal"),
                SignalOption(label="Former employee/partner using old login", refined_tag="account_compromised")
            ]
        )
    ]
}

def get_signals_for_tag(tag: str) -> List[SignalDefinition]:
    return SIGNAL_REGISTRY.get(tag, [])

def map_answer_to_tag(tag: str, signal_name: str, answer_label: str) -> Optional[str]:
    signals = get_signals_for_tag(tag)
    for s in signals:
        if s.signal_name == signal_name:
            for opt in s.options:
                if opt.label == answer_label:
                    return opt.refined_tag
    return None
