from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator, Optional

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession

from temporalio import common
from temporalio.client import (
    Client,
    WithStartWorkflowOperation,
)

from workflow import LoanProcessingWorkflow
from agent import LoanApplication, LoanDecision

@dataclass(slots=True)
class AppContext:
    """Shared objects created during FastMCP lifespan startup."""

    temporal_client: Client

@asynccontextmanager
async def server_lifespan(_: FastMCP) -> AsyncIterator[AppContext]:
    """Create and tear down shared server resources."""

    client = await Client.connect("localhost:7233")
    yield AppContext(temporal_client=client)

def _application_id_from_context(context: Context | None) -> Optional[str]:
    """Extract the application id from the provided MCP context."""
    if not context:
        return None

    # Check HTTP headers for session ID
    try:
        headers = context.request_context.request.headers
        if session_id := headers.get("x-ms-client-session-id"):
            return f"APP_{session_id.strip()}"
    except AttributeError:
        pass

    return None

server: FastMCP[AppContext] = FastMCP("pydantic-ai-server", stateless_http=True, lifespan=server_lifespan)

@server.tool()
async def start_loan_application(
    applicant_name: str,
    annual_income: float,
    requested_loan_amount: float,
    property_value: float,
    context: Context[ServerSession, AppContext] | None = None,
) -> dict:
    application_id = _application_id_from_context(context)

    application = LoanApplication(
        application_id=application_id,
        applicant_name=applicant_name,
        annual_income=annual_income,
        requested_loan_amount=requested_loan_amount,
        property_value=property_value,
    )

    start_operation = WithStartWorkflowOperation(
        LoanProcessingWorkflow.run,
        id=application_id,
        task_queue="home-loan-agent",
        id_conflict_policy=common.WorkflowIDConflictPolicy.USE_EXISTING,
    )

    try:
        client = context.request_context.lifespan_context.temporal_client
        decision_payload = await client.execute_update_with_start_workflow(
            LoanProcessingWorkflow.start_processing,
            application.model_dump(),
            start_workflow_operation=start_operation,
        )
        decision = LoanDecision.model_validate(decision_payload)
    except Exception as exc:
        return {
            "application_id": application_id,
            "status": "processing_failed",
            "error": str(exc),
        }

    return {
        "application_id": application_id,
        "status": f"decision_{decision.recommendation}",
        "decision": decision.model_dump(),
    }


@server.tool()
async def supply_bank_account(
    bank_account_number: str,
    context: Context[ServerSession, AppContext] | None = None,
) -> dict:
    application_id = _application_id_from_context(context)

    try:
        client = context.request_context.lifespan_context.temporal_client
        handle = client.get_workflow_handle(application_id)
        update_result = await handle.execute_update(
            LoanProcessingWorkflow.supply_bank_account,
            bank_account_number,
        )
    except Exception as exc:
        return {
            "application_id": application_id,
            "status": "update_failed",
            "error": str(exc),
        }

    return update_result


@server.tool()
async def get_application_status(
    context: Context[ServerSession, AppContext] | None = None,
) -> dict:
    application_id = _application_id_from_context(context)

    try:
        client = context.request_context.lifespan_context.temporal_client
        handle = client.get_workflow_handle(application_id)
        status_info = await handle.query(LoanProcessingWorkflow.status)
    except Exception as exc:
        return {
            "application_id": application_id,
            "status": "query_failed",
            "error": str(exc),
        }

    return status_info


def run_server(transport: str = "streamable-http") -> None:
    """Run the FastMCP server with the provided transport."""
    server.run(transport=transport)


if __name__ == "__main__":
    run_server()
