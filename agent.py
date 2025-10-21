from __future__ import annotations

import json
from typing import Any, Literal, Optional
from urllib import error, request

from temporalio import workflow

from pydantic import BaseModel, Field, computed_field
from pydantic_ai import Agent, RunContext

with workflow.unsafe.imports_passed_through():
    from config import settings

class LoanApplication(BaseModel):
    """Structured loan application information passed into the agent."""

    application_id: str = Field(..., description="Internal application identifier")
    applicant_name: str
    annual_income: float = Field(
        ..., gt=0, description="Documented gross annual income in USD"
    )
    requested_loan_amount: float = Field(
        ..., gt=0, description="Requested loan principal in USD"
    )
    property_value: float = Field(
        ..., gt=0, description="Estimated property value in USD"
    )

    @computed_field
    @property
    def loan_to_value_ratio(self) -> float:
        return self.requested_loan_amount / self.property_value

    @computed_field
    @property
    def debt_to_income_ratio(self) -> float:
        monthly_income = self.annual_income / 12
        estimated_monthly_payment = self.requested_loan_amount * 0.005
        return estimated_monthly_payment / monthly_income


class UnderwritingRecommendation(BaseModel):
    """Agent-authored underwriting recommendation."""

    recommendation: Literal["approve", "review", "decline"]
    approved_amount: Optional[float] = Field(
        None, ge=0, description="Maximum principal the agent recommends approving"
    )
    risk_factors: Optional[list[str]] = None
    requested_docs: list[str] = Field(default_factory=list)
    additional_questions: list[str] = Field(
        default_factory=list,
        description="Follow-up questions to gather more borrower details or account info",
    )
    summary: Optional[str] = None
    
    @property
    def done(self) -> float:
        return self.recommendation in ["approve", "decline"]


class FinalResult(BaseModel):
    """Final loan application result."""
    
    application_id: str
    final_decision: Literal["approved", "rejected"]
    reason: str
    approved_amount: Optional[float] = None


underwriter_agent = Agent[None, [FinalResult, UnderwritingRecommendation]](
    settings.model_name,
    system_prompt=(
        "You are a home loan underwriter. "
        "You guide customer to provide the details of their loan. "
        "You analyze the provided loan application, gather any missing financial context "
        "Reject application with debt to income ratio above 0.5. "
        "Always ask for bank account number before making a underwriting recommendation. "
        "Always use tool to ask for human approval before returning the final result. "
    ),
    name="underwriter",
    output_type=[FinalResult, UnderwritingRecommendation],
)


@underwriter_agent.tool
async def fetch_bank_statement(
    _context: RunContext[None], account_number: str
) -> dict[str, Any]:
    """Fetch a FakeBank statement for the requested account number."""

    statement: dict = None
    url = f"{settings.fake_bank_url}/accounts/{account_number}"

    try:
        req = request.Request(url, headers={"Accept": "application/json"})
        with request.urlopen(req, timeout=5) as response:
            charset_getter = getattr(response.headers, "get_content_charset", None)
            charset = charset_getter() if callable(charset_getter) else None
            payload = response.read().decode(charset or "utf-8")
            statement = json.loads(payload)
    except error.HTTPError as exc:
        return {
            "account_number": account_number,
            "status": "error",
            "error": f"FakeBank returned HTTP {exc.code}: {exc.reason}",
        }

    return {
        "account_number": account_number,
        "status": "ok",
        "statement": statement,
    }


@underwriter_agent.tool
async def ask_for_approval(
    _context: RunContext[None], 
    application: LoanApplication,
    recommendation: UnderwritingRecommendation,
) -> dict[str, Any]:
    """Post loan application details to MS Teams for approval."""
    
    if not settings.teams_webhook_url:
        return {"status": "error", "error": "Teams webhook URL not configured"}
    
    facts = [
        {"name": "Applicant", "value": application.applicant_name},
        {"name": "Annual Income", "value": f"${application.annual_income:,.2f}"},
        {"name": "Requested Amount", "value": f"${application.requested_loan_amount:,.2f}"},
        {"name": "Property Value", "value": f"${application.property_value:,.2f}"},
        {"name": "LTV Ratio", "value": f"{application.loan_to_value_ratio*100:.1f}%"},
        {"name": "DTI Ratio", "value": f"{application.debt_to_income_ratio*100:.1f}%"}
    ]
    
    for field, name in [(recommendation.approved_amount, "Approved Amount"), (recommendation.risk_factors, "Risk Factors"), (recommendation.requested_docs, "Requested Docs")]:
        if field:
            value = f"${field:,.2f}" if name == "Approved Amount" else "; ".join(field)
            facts.append({"name": name, "value": value})
    
    sections = [{
        "activityTitle": f"Loan Application {application.application_id}",
        "activitySubtitle": f"Recommendation: {recommendation.recommendation.title()}",
        "facts": facts
    }]
    
    for field, title in [(recommendation.summary, "Summary"), (recommendation.additional_questions, "Additional Questions")]:
        if field:
            text = field if title == "Summary" else "\n".join(field)
            sections.append({"activityTitle": title, "text": text})
    
    card = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": "0076D7",
        "summary": f"Loan Application {application.application_id} - {recommendation.recommendation.title()}",
        "sections": sections,
        "potentialAction": [
            {
                "@type": "OpenUri",
                "name": "Approve",
                "targets": [{"os": "default", "uri": f"{settings.approval_base_url}/applications/{application.application_id}?action=approve"}]
            },
            {
                "@type": "OpenUri",
                "name": "Reject",
                "targets": [{"os": "default", "uri": f"{settings.approval_base_url}/applications/{application.application_id}?action=reject"}]
            }
        ]
    }
    
    try:
        data = json.dumps(card).encode('utf-8')
        req = request.Request(settings.teams_webhook_url, data=data, headers={'Content-Type': 'application/json'})
        with request.urlopen(req, timeout=10) as response:
            return {"status": "success" if response.status == 200 else "error", 
                    "message": "Posted to Teams successfully" if response.status == 200 else f"HTTP {response.status}"}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
