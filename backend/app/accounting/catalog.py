from typing import Final

from app.accounting.models import GLAccount, GLSelectionValidation

NORTHSTAR_GL_CATALOG: Final[tuple[GLAccount, ...]] = (
    GLAccount(account_id="6100", label="Cleaning services", category="cleaning"),
    GLAccount(account_id="6110", label="Maintenance and repairs", category="maintenance"),
    GLAccount(account_id="6120", label="Electrical services", category="electrical"),
    GLAccount(account_id="6130", label="Plumbing services", category="plumbing"),
    GLAccount(account_id="6140", label="Equipment and tools", category="equipment"),
    GLAccount(account_id="6170", label="Fuel and transport", category="fuel"),
)


def get_northstar_gl_catalog() -> tuple[GLAccount, ...]:
    return NORTHSTAR_GL_CATALOG


def validate_gl_selection(account_id: str | None) -> GLSelectionValidation:
    if account_id is None or not account_id.strip():
        return GLSelectionValidation(
            account_id=None,
            valid=False,
            reason="Select a Northstar GL account before approval.",
        )

    if account_id not in {account.account_id for account in NORTHSTAR_GL_CATALOG}:
        return GLSelectionValidation(
            account_id=account_id,
            valid=False,
            reason="The selected account is not in the Northstar GL catalog.",
        )

    return GLSelectionValidation(account_id=account_id, valid=True)
