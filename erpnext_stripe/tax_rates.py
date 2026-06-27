from frappe.utils.data import flt


def get_tax_rate_region(tax_rate) -> str | None:
	region_parts = []
	for part in (
		getattr(tax_rate, "country", None),
		getattr(tax_rate, "state", None),
		getattr(tax_rate, "jurisdiction", None),
	):
		if part and part not in region_parts:
			region_parts.append(part)

	region = " - ".join(region_parts)
	return region or getattr(tax_rate, "display_name", None) or getattr(tax_rate, "description", None)


def get_tax_rate_percentage(tax_rate) -> float:
	percentage = getattr(tax_rate, "effective_percentage", None)
	if percentage is None:
		percentage = tax_rate.percentage

	return flt(percentage)


def get_tax_rate_calculation(tax_rate) -> str:
	return "Inclusive" if tax_rate.inclusive else "Exclusive"


def get_tax_rate_data(tax_rate) -> dict:
	return {
		"stripe_id": tax_rate.id,
		"region": get_tax_rate_region(tax_rate),
		"description": getattr(tax_rate, "description", None),
		"rate": get_tax_rate_percentage(tax_rate),
		"inclusive": tax_rate.inclusive,
	}
