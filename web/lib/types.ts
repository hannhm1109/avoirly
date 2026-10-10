export type Status =
  | "PENDING"
  | "PROCESSING"
  | "NEEDS_REVIEW"
  | "NO_DISCREPANCY"
  | "DISCREPANCY_FOUND"
  | "CLAIM_DRAFTED"
  | "CLAIM_SENT"
  | "AWAITING_RESPONSE"
  | "CREDIT_PROMISED"
  | "CREDIT_CONFIRMED"
  | "FAILED"
  | "CLOSED";
export type Role = "PO" | "INVOICE";
export interface Source {
  page: number;
  text: string | null;
}
export interface Line {
  line_number: number;
  sku: string | null;
  description: string | null;
  quantity: string | null;
  unit: string | null;
  unit_price: string | null;
  tax_rate: string | null;
  line_total: string | null;
  source: Source;
}
export interface DocumentData {
  document_type: string;
  document_number: string | null;
  document_date: string | null;
  currency: string | null;
  supplier: { name: string | null; tax_id: string | null };
  buyer: { name: string | null; tax_id: string | null };
  prices_include_tax: boolean | null;
  adjustments_present: boolean | null;
  line_items: Line[];
  subtotal: string | null;
  tax_total: string | null;
  total: string | null;
  warnings: string[];
  due_date?: string | null;
  purchase_order_reference?: string | null;
}
export interface Pair {
  purchase_order: DocumentData;
  invoice: DocumentData;
}
export interface ReviewIssue {
  code: string;
  document_role: Role | "PAIR";
  line_number: number | null;
  field: string | null;
  message: string;
}
export interface Finding {
  po_line_number: number;
  invoice_line_number: number;
  reasons: string[];
  ordered_quantity: string;
  invoiced_quantity: string;
  po_unit_price: string;
  invoice_unit_price: string;
  quantity_component_net: string;
  price_component_net: string;
  potential_credit_net: string;
  po_source: Source;
  invoice_source: Source;
}
export interface Comparison {
  outcome: string;
  currency: string | null;
  findings: Finding[];
  review_issues: ReviewIssue[];
  potential_credit_net: string | null;
  warnings: string[];
}
export interface CaseSummary {
  id: string;
  status: Status;
  version: number;
  current_revision: number;
  processing_step: string | null;
  currency: string | null;
  potential_credit_net: string | null;
  close_reason: string | null;
  error_code: string | null;
  created_at: string;
  updated_at: string;
  supplier_name?: string | null;
  invoice_number?: string | null;
  po_number?: string | null;
  recovery?: RecoverySummary;
}
export interface CaseDetail extends CaseSummary {
  recovery: RecoveryDetail;
  documents: Partial<
    Record<
      Role,
      {
        id: string;
        original_name: string;
        mime_type: string;
        page_count: number;
      }
    >
  >;
  extractions: Partial<
    Record<
      Role,
      {
        id: string;
        version: number;
        raw: DocumentData;
        corrected: DocumentData | null;
      }
    >
  >;
  comparison: Comparison | null;
  review_issues: ReviewIssue[];
  draft: {
    id: string;
    version: number;
    subject: string;
    body: string;
    language: "fr" | "en";
  } | null;
  jobs: {
    id: string;
    status: string;
    attempt: number;
    revision: number;
    error_code: string | null;
  }[];
}
export interface CasePage {
  items: CaseSummary[];
  limit: number;
  offset: number;
  potential_credit_by_currency: Record<string, string>;
  recovery_by_currency: Record<
    "sent" | "promised" | "confirmed",
    Record<string, string>
  >;
}

export interface RecoverySummary {
  currency: string | null;
  sent_net: string;
  promised_net: string;
  confirmed_net: string;
  remaining_claim_net: string;
  has_sent_record: boolean;
  fully_credited: boolean;
}
export interface RecoveryEntry {
  id: string;
  kind: "SENT" | "NOTE" | "PROMISE" | "CREDIT";
  revision: number;
  occurred_on: string;
  amount_net: string | null;
  currency: string;
  reference: string;
  note: string;
  due_on: string | null;
  evidence_id: string | null;
  snapshot: { subject?: string; body?: string; draft_version?: number };
  actor_id: string;
  created_at: string;
  voided_at: string | null;
  void_reason: string | null;
}
export interface RecoveryDetail extends RecoverySummary {
  entries: RecoveryEntry[];
  evidence: {
    id: string;
    original_name: string;
    mime_type: string;
    page_count: number;
    sha256: string;
    created_at: string;
  }[];
}
