// types/index.ts — shared TypeScript types

export interface Product {
  id:                   number;
  pzn:                  number;
  name:                 string;
  price:                number;
  package_size:         string;
  description:          string;
  stock_quantity:       number;
  prescription_required: boolean;
}

export interface OrderResponse {
  order_id:                string | null;
  order_status:            "approved" | "rejected" | "pending" | "needs_clarification" | null;
  final_response:          string;
  triage_suggestion:       string | null;
  product_id:              number | null;
  product_name:            string | null;
  quantity:                number | null;
  unit_price:              number | null;
  total_price:             number | null;
  dosage:                  string | null;
  safety_approved:         boolean | null;
  safety_reason:           string | null;
  new_stock_level:         number | null;
  refill_alert:            boolean | null;
  refill_medicine:         string | null;
  refill_due_date:         string | null;
  webhook_triggered:       boolean | null;
  notification_sent:       boolean | null;
  langfuse_trace_id:       string | null;
  agent_log:               AgentLogEntry[];
  payment_method:          string | null;
  payment_status:          string | null;
  prescription_uploaded:   boolean | null;
  pending_product_options: unknown[] | null;
  // Intent field for proactive messages (e.g., "PROACTIVE_REFILL")
  intent?:                 string | null;
}

export interface AgentLogEntry {
  timestamp: string;
  agent:     string;
  action:    string;
  details:   Record<string, unknown>;
}

export interface ChatMessage {
  id:         string;
  role:       "user" | "assistant";
  content:    string;
  timestamp:  Date;
  meta?:      OrderResponse;
  cartState?: "pending_review" | "confirmed"; // tracks cart UI state
}

export interface RefillAlert {
  id:                    string;
  user_id:               string;
  product_id:            number;
  last_purchase:         string;
  predicted_refill_date: string;
  alert_sent:            boolean;
  status:                string;
  products?:             { name: string; price: number };
  users?:                { patient_id: string; age: number; gender: string };
}

export interface Decision {
  id:                string;
  order_id:          string | null;
  agent_name:         string;
  action:            string;
  reason:            string;
  input_payload:     Record<string, unknown> | null;
  output_payload:    Record<string, unknown> | null;
  langfuse_trace_id: string | null;
  created_at:        string;
}

export interface LowStockAlert {
  product_id: number;
  pzn: number;
  name: string;
  price: number;
  package_size: string;
  description: string;
  stock_quantity: number;
  prescription_required: boolean;
  threshold: number;
  severity: "critical" | "warning";
}

export interface LowStockAlertsResponse {
  count: number;
  threshold: number;
  alerts: LowStockAlert[];
}
