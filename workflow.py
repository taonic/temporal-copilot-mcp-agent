from __future__ import annotations

from typing import Optional

from pydantic_ai.durable_exec.temporal import TemporalAgent
from pydantic_ai.messages import ModelMessage
from temporalio import workflow

from agent import (
    LoanApplication,
    LoanDecision,
    underwriter_agent,
)

@workflow.defn
class LoanProcessingWorkflow:
    def __init__(self) -> None:
        self._agent: TemporalAgent = TemporalAgent(underwriter_agent)
        self._application: Optional[LoanApplication] = None
        self._decision: Optional[LoanDecision] = None
        self._bank_account_number: Optional[str] = None
        self._message_history: list[ModelMessage] = None

    @workflow.run
    async def run(self) -> LoanDecision:
        await workflow.wait_condition(lambda: self._decision and self._decision.done)
        return self._decision

    @workflow.update
    async def start_processing(self, payload: dict) -> LoanDecision:
        try:
            self._application = LoanApplication.model_validate(payload)
        except Exception as e:
            raise ValueError(f"Invalid loan application data: {e}")
        result = await self._agent.run(self._application.model_dump_json())
        self._message_history = result.all_messages()
        self._decision = result.output
        return self._decision

    @workflow.update
    async def supply_bank_account(self, account_number: str) -> dict:
        prompt = f"The borrower has now provided bank account number {account_number}."
        result = await self._agent.run(
            prompt,
            message_history=self._message_history
        )
        self._message_history = result.all_messages()
        self._decision = result.output
        return {
            "application_id": self._application.application_id,
            "status": f"decision_{self._decision.recommendation}",
            "decision": self._decision.model_dump(),
            "bank_account_number": account_number,
        }

    @workflow.query
    def status(self) -> dict:
        return {
            "application_id": self._application.application_id,
            "decision": self._decision.model_dump() if self._decision else None,
        }
