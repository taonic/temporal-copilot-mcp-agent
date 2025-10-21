from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict


class Transaction(BaseModel):
    kind: str
    description: str
    amount: float


class Statement(BaseModel):
    account_id: str
    account_name: str
    salary: float
    expenses: float
    balance: float
    transactions: List[Transaction]


app = FastAPI(title="FakeBank API", version="1.0.0")

_fake_statements: Dict[str, Statement] = {
    "123-456": Statement(
        account_id="acc1",
        account_name="Tao",
        salary=12500.0,
        expenses=3200.0,
        balance=8100.0,
        transactions=[
            Transaction(kind="salary", description="Monthly salary", amount=12500.0),
            Transaction(kind="expense", description="Office lease", amount=-1500.0),
            Transaction(kind="expense", description="Cloud services", amount=-900.0),
            Transaction(kind="expense", description="Team lunch", amount=-300.0),
            Transaction(kind="expense", description="Utilities", amount=-500.0),
        ],
    ),
    "654-321": Statement(
        account_id="acc2",
        account_name="Bob",
        salary=3500.0,
        expenses=4100.0,
        balance=-600.0,
        transactions=[
            Transaction(kind="salary", description="Monthly revenue payout", amount=3500.0),
            Transaction(kind="expense", description="Supply restock", amount=-1800.0),
            Transaction(kind="expense", description="Staff wages", amount=-1500.0),
            Transaction(kind="expense", description="Utility bills", amount=-500.0),
            Transaction(kind="expense", description="Local advertising", amount=-300.0),
        ],
    ),
}


@app.get("/accounts/{account_id}", response_model=Statement)
def get_statement(account_id: str) -> Statement:
    """
    Return a fake bank statement for the requested account.
    """
    if account_id not in _fake_statements:
        raise HTTPException(status_code=404, detail="Account not found")
    return _fake_statements[account_id]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("fakebank.main:app", host="127.0.0.1", port=8001)
