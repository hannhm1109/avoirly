export type Status =
  | "PENDING"
  | "PROCESSING"
  | "NEEDS_REVIEW"
  | "NO_DISCREPANCY"
  | "DISCREPANCY_FOUND"
  | "CLAIM_DRAFTED"
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
}
export interface CaseDetail extends CaseSummary {
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
}
