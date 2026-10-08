# ============================================================================
# Payroll — pay runs, withholding, pay stubs, direct deposit
# Posts: DR Wages Expense + DR Payroll Tax Expense, CR tax/deduction payables,
#        CR Bank for net pay.
# ============================================================================

from fastapi import APIRouter

router = APIRouter(prefix="/api/payroll", tags=["payroll"])
