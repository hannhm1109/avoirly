"""Professional claim drafts from validated facts, with no sending capability."""

from .comparison import compare
from .models import ClaimDraft, ComparisonResult, ValidatedPair


def clean(value):
    # Prevent document text from introducing extra mail headers or control characters.
    return " ".join(value.split())


def generate_claim(pair: ValidatedPair, result: ComparisonResult, language="fr") -> ClaimDraft:
    if language not in ("fr", "en"):
        raise ValueError("Supported languages: fr, en.")
    if result.outcome != "DISCREPANCY_FOUND" or result != compare(pair):
        raise ValueError("A complete, current discrepancy comparison is required for a draft.")
    po, inv = pair.purchase_order, pair.invoice
    po_number, invoice_number = clean(po.document_number), clean(inv.document_number)
    currency, amount = inv.currency, f"{result.potential_credit_net:.2f}"
    by_number = {r.line_number: r for r in inv.line_items}
    rows = []
    for f in result.findings:
        row = by_number[f.invoice_line_number]
        desc = clean(row.description)
        if language == "fr":
            rows.append(
                f"- {desc} : quantité commandée {f.ordered_quantity} {row.unit}, "
                f"facturée {f.invoiced_quantity} {row.unit} ; prix unitaire HT commande "
                f"{f.po_unit_price} {currency}, facture {f.invoice_unit_price} {currency} ; "
                f"écart potentiel HT {f.potential_credit_net:.2f} {currency}."
            )
        else:
            rows.append(
                f"- {desc}: ordered {f.ordered_quantity} {row.unit}, "
                f"invoiced {f.invoiced_quantity} {row.unit}; net unit price on PO "
                f"{f.po_unit_price} {currency}, on invoice {f.invoice_unit_price} {currency}; "
                f"potential difference excluding tax {f.potential_credit_net:.2f} {currency}."
            )
    details = "\n".join(rows)
    buyer = clean(inv.buyer.name)
    if language == "fr":
        subject = f"Demande de vérification — facture {invoice_number} / commande {po_number}"
        body = (
            f"Bonjour,\n\nAprès rapprochement de votre facture {invoice_number} avec notre "
            f"bon de commande {po_number}, nous avons relevé les écarts suivants :\n\n{details}\n\n"
            f"Le montant potentiel de l’écart hors taxes est de {amount} {currency}. "
            "Pourriez-vous vérifier ces éléments et, si l’écart est confirmé, nous transmettre "
            "un avoir correspondant ? Si une modification de commande explique cet écart, "
            "merci de nous la communiquer.\n\nNous vous remercions pour votre retour.\n\n"
            f"Cordialement,\n{buyer}\n"
        )
    else:
        subject = f"Verification request — invoice {invoice_number} / purchase order {po_number}"
        body = (
            f"Hello,\n\nAfter comparing your invoice {invoice_number} with our purchase order "
            f"{po_number}, we identified the following differences:\n\n{details}\n\n"
            f"The potential difference excluding tax is {amount} {currency}. Please verify "
            "these details and, if confirmed, issue a corresponding credit note. If an agreed "
            "order amendment explains the difference, please share it with us.\n\n"
            f"Thank you for your assistance.\n\nKind regards,\n{buyer}\n"
        )
    return ClaimDraft(subject=subject, body=body, language=language)
