# Skill: invoice-format (house format for invoice extraction)

When extracting invoices, write ONE JSON file per invoice to out/<invoice_number>.json with exactly these keys:

- "inv_no": the invoice number as a string, without any "INV-" prefix
- "vendor": vendor name in UPPER CASE
- "date": ISO format YYYY-MM-DD
- "total_cents": the total as an integer number of cents (e.g. $1,234.50 -> 123450)
- "currency": three-letter code, default "USD" if not stated

Do not add other keys.
