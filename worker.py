from __future__ import annotations

import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from pydantic_ai.durable_exec.temporal import (
    AgentPlugin,
    TemporalAgent,
    PydanticAIPlugin
)

from workflow import LoanProcessingWorkflow
from agent import underwriter_agent


async def run_temporal_worker() -> None:
    client = await Client.connect("localhost:7233", plugins=[PydanticAIPlugin()])
    worker = Worker(
        client,
        task_queue="home-loan-agent",
        workflows=[LoanProcessingWorkflow],
        plugins=[AgentPlugin(TemporalAgent(underwriter_agent))],
    )

    print("LoanProcessingWorkflow worker started. Awaiting tasks...")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(run_temporal_worker())
