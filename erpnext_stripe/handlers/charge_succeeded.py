from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from stripe import Event


from erpnext_stripe.operations.create_bank_transaction import run_for_charge as create_bank_transaction


def handle(event: "Event", ignore_permissions: bool = False):
	create_bank_transaction(event.data.object, ignore_permissions=ignore_permissions)
