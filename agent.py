from __future__ import annotations

import asyncio
import json
from typing import Any, Literal, Optional
from urllib import error, request

from pydantic import BaseModel, Field, computed_field
from pydantic_ai import Agent, RunContext

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


class LoanDecision(BaseModel):
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


underwriter_agent = Agent[None, LoanDecision](
    settings.model_name,
    system_prompt=(
        "You are a home loan underwriter. "
        "You guide customer to provide the details of their loan. "
        "You analyze the provided loan application, gather any missing financial context "
        "Reject application with debt to income ratio above 0.5. "
        "Ask for bank account details if needed and verify with fetch_bank_statement. "
        "Do not approve if bank account details is not verified. "
        "Use the LoanDecision schema to summarize your decision. "
    ),
    name="underwriter",
    output_type=LoanDecision,
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
