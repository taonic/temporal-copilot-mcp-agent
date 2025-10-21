from __future__ import annotations

from typing import Optional

from pydantic_ai.durable_exec.temporal import TemporalAgent
from pydantic_ai.messages import ModelMessage
from temporalio import workflow

from agent import (
    LoanApplication,
    UnderwritingRecommendation,
    FinalResult,
    underwriter_agent,
)

@workflow.defn
class LoanProcessingWorkflow:
    def __init__(self) -> None:
        self._agent: TemporalAgent = TemporalAgent(underwriter_agent)
        self._application: Optional[LoanApplication] = None
        self._final_decision: Optional[FinalResult] = None
        self._human_decision: str = None
        self._bank_account_number: Optional[str] = None
        self._message_history: list[ModelMessage] = None

    @workflow.run
    async def run(self) -> FinalResult:
        await workflow.wait_condition(lambda: self._final_decision is not None)
        return self._final_decision

    @workflow.update
    async def start_processing(self, payload: dict) -> UnderwritingRecommendation:
        try:
            self._application = LoanApplication.model_validate(payload)
        except Exception as e:
            raise ValueError(f"Invalid loan application data: {e}")
        result = await self._agent.run(self._application.model_dump_json())
        self._message_history = result.all_messages()
        return result.output

    @workflow.update
    async def supply_bank_account(self, account_number: str) -> dict:
        prompt = f"The borrower has now provided bank account number {account_number}."
        result = await self._agent.run(
            prompt,
            message_history=self._message_history
        )
        self._message_history = result.all_messages()
        
        # Wait for human decision to come from signal
        await workflow.wait_condition(lambda: self._human_decision != None)
        
        prompt = f"The human underwriter has made the final decision: {self._human_decision}."
        result = await self._agent.run(
            prompt,
            message_history=self._message_history
        )
        self._final_decision = result.output
        
        return result.output

    @workflow.signal
    async def receive_human_decision(self, decision: str):
        self._human_decision = decision

    @workflow.query
    def status(self) -> dict:
        return {
            "application_id": self._application.application_id,
            "decision": self._final_decision.model_dump() if self._final_decision else None,
        }
