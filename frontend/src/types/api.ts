/** Shared API types mirroring the FastAPI schemas. */

export type PriorityLabel = "critical" | "high" | "medium" | "low";

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  role: string;
  username: string;
}

export interface FtfRecord {
  id: string;
  drug_name: string;
  dosage_form?: string | null;
  strength?: string | null;
  rld_nda?: string | null;
  rld_brand_name?: string | null;
  nda_number?: string | null;
  date_of_submission?: string | null;
  number_of_andas?: number | null;
  exclusivity_status?: string | null;
  decision_posting_date?: string | null;
  first_applicant_approval_date?: string | null;
  first_commercial_marketing_date?: string | null;
  last_qualifying_patent_expiry?: string | null;
  certification_type?: string | null;
  source_code: string;
  first_seen_at: string;
  drug_id?: string | null;
  patent_id?: string | null;
}

export interface PteApplication {
  id: string;
  application_number: string;
  patent_number: string;
  filing_date?: string | null;
  trade_name?: string | null;
  generic_name?: string | null;
  designated_number?: string | null;
  sponsor_name?: string | null;
  status?: string | null;
  source_code: string;
}

export interface PteCertificate {
  id: string;
  patent_number: string;
  trade_name?: string | null;
  generic_name?: string | null;
  sponsor_name?: string | null;
  original_expiration_date?: string | null;
  extended_expiration_date?: string | null;
  extension_days?: number | null;
  extension_text?: string | null;
  granted_date?: string | null;
  status?: string | null;
  source_code: string;
}

export interface ActiveMoiety {
  id: string;
  moiety_name: string;
  sponsor_name?: string | null;
  date_issued?: string | null;
  approval_year?: number | null;
  status?: string | null;
  source_code: string;
  drug_id?: string | null;
}

export interface OrangeBookProduct {
  id: string;
  appl_type: string;
  appl_no: string;
  product_no?: string | null;
  ingredient?: string | null;
  trade_name?: string | null;
  applicant?: string | null;
  applicant_full_name?: string | null;
  strength?: string | null;
  dosage_form_route?: string | null;
  te_code?: string | null;
  approval_date?: string | null;
  rld?: boolean | null;
  rs?: boolean | null;
  product_type?: string | null;
}

export interface OrangeBookPatent {
  id: string;
  appl_type: string;
  appl_no: string;
  product_no?: string | null;
  patent_number: string;
  expiration_date?: string | null;
  drug_substance_flag?: boolean | null;
  drug_product_flag?: boolean | null;
  patent_use_code?: string | null;
  delist_flag?: boolean | null;
}

export interface OrangeBookSupplement {
  id: string;
  supplement_number: string;
  edition?: string | null;
  publication_month?: number | null;
  publication_year?: number | null;
  publication_date?: string | null;
  is_current: boolean;
  products_added?: number | null;
  products_removed?: number | null;
  products_modified?: number | null;
}

export interface DetectedChange {
  id: string;
  module: string;
  source_code: string;
  entity_type: string;
  change_type: "added" | "updated" | "removed";
  source_key: string;
  detected_at: string;
  is_baseline: boolean;
  field_changes?: Array<{ field: string; before: unknown; after: unknown }> | null;
  before?: Record<string, unknown> | null;
  after?: Record<string, unknown> | null;
}

export interface ScoreComponent {
  name: string;
  raw: number;
  weight: number;
  points: number;
  reason?: string | null;
}

export interface ScoreBreakdown {
  total: number;
  label: PriorityLabel | string;
  components: ScoreComponent[];
}

export interface Insight {
  id: string;
  module: string;
  entity_type: string;
  entity_key: string;
  title: string;
  what_changed?: string | null;
  why_it_matters?: string | null;
  affected_companies?: string[] | null;
  affected_products?: string[] | null;
  generic_opportunity?: string | null;
  exclusivity_risk?: string | null;
  recommended_action?: string | null;
  priority_score: number;
  priority_label: PriorityLabel;
  score_breakdown?: ScoreBreakdown | Record<string, number> | null;
  generated_by?: string | null;
  confidence?: number | null;
  created_at: string;
}

export interface Alert {
  id: string;
  module: string;
  event_type: string;
  severity: string;
  title: string;
  message?: string | null;
  priority_score: number;
  priority_label: PriorityLabel;
  status: string;
  entity_type?: string | null;
  entity_key?: string | null;
  drug_name?: string | null;
  sponsor_name?: string | null;
  insight_id?: string | null;
  channels_sent?: string[] | null;
  acknowledged_by?: string | null;
  created_at: string;
}

export interface Kpis {
  drugs_monitored: number;
  patents_expiring_soon: number;
  new_ftf_records: number;
  new_pte_applications: number;
  new_pte_grants: number;
  new_active_moieties: number;
  orange_book_updates: number;
  open_alerts: number;
  high_risk_opportunities: number;
  changes_last_30_days: number;
  insights_total: number;
}

export interface AlertSummary {
  total: number;
  open: number;
  critical: number;
  high: number;
  medium: number;
  low: number;
  open_total?: number;
  by_priority?: Record<string, number>;
  by_module?: Record<string, number>;
}

export interface FtfSummary {
  total_filings: number;
  eligible_180_day: number;
  extinguished_180_day: number;
  deferred: number;
  filings_last_12_months: number;
  patents_expiring_24_months: number;
}

export interface PteSummary {
  applications_total: number;
  certificates_total: number;
  applications_last_12_months: number;
  certificates_last_12_months: number;
  average_extension_days: number | null;
}

export interface PdeSummary {
  total_moieties: number;
  approved_last_12_months: number;
  distinct_sponsors: number;
}

export interface OrangeBookSummary {
  total_products: number;
  nda_products: number;
  anda_products: number;
  patent_listings: number;
  exclusivity_grants: number;
  current_supplement?: {
    number?: string | null;
    edition?: string | null;
    publication_month?: number | null;
    publication_year?: number | null;
  } | null;
}

export interface GraphStats {
  node_count: number;
  edge_count: number;
  nodes_by_type?: Record<string, number>;
  edges_by_relation?: Record<string, number>;
}

export interface SearchHit {
  entity_type: string;
  id: string;
  title: string;
  subtitle?: string | null;
  score: number;
  matched_on: string;
  attributes: Record<string, unknown>;
  url?: string | null;
}

export interface SearchResult {
  query: string;
  interpreted_as: Record<string, unknown>;
  total: number;
  hits: SearchHit[];
  facets: Record<string, number>;
}

export interface CopilotToolCall {
  name: string;
  arguments: Record<string, unknown>;
  error?: string | null;
  result_summary?: unknown;
}

export interface CopilotAnswer {
  question: string;
  answer: string;
  intent: string;
  tool_calls: CopilotToolCall[];
  citations: Array<Record<string, unknown>>;
  model: string;
  provider: string;
  latency_ms: number;
  data: Record<string, unknown>;
}

export interface SourceDefinition {
  id: string;
  code: string;
  name: string;
  module: string;
  url: string;
  document_kind?: string | null;
  cadence?: string | null;
  description?: string | null;
  enabled: boolean;
  last_checked_at?: string | null;
  last_success_at?: string | null;
  last_error?: string | null;
}

export interface PipelineRun {
  id: string;
  trigger: string;
  status: string;
  started_at: string;
  finished_at?: string | null;
  duration_ms?: number | null;
  sources_checked?: number | null;
  sources_changed?: number | null;
  changes_detected?: number | null;
  insights_generated?: number | null;
  alerts_created?: number | null;
  summary?: Record<string, unknown> | null;
  error?: string | null;
}

export interface SavedView {
  id: string;
  name: string;
  module?: string | null;
  description?: string | null;
  filters: Record<string, unknown>;
  is_shared: boolean;
  owner?: string | null;
  created_at: string;
}

export interface ChartPoint {
  [key: string]: string | number | null;
}

export interface DashboardCharts {
  patent_expiry_timeline: Array<{ year: number; count: number }>;
  sponsor_leaderboard: Array<Record<string, string | number>>;
  therapy_area_analysis: Array<{ therapy_area: string; drugs: number; ftf_filings: number }>;
  monthly_fda_activity: Array<Record<string, string | number>>;
  generic_opportunity_heatmap: Array<Record<string, string | number | null>>;
  patent_family_distribution: Array<{ assignee: string; patents: number }>;
}

export interface GraphNode {
  id: string;
  type: string;
  key: string;
  label: string;
  ref_table?: string | null;
  ref_id?: string | null;
  properties: Record<string, unknown>;
  importance: number;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  relation: string;
  weight: number;
  properties: Record<string, unknown>;
}

export interface GraphNeighborhood {
  root: GraphNode;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface RealtimeEvent {
  topic: string;
  event_type?: string;
  payload: Record<string, unknown>;
  event_id?: string;
  occurred_at?: string;
  source?: string;
  version?: number;
}

export interface AuditLogEntry {
  id: string;
  actor?: string | null;
  action: string;
  resource_type?: string | null;
  resource_id?: string | null;
  detail?: Record<string, unknown> | null;
  ip_address?: string | null;
  created_at?: string | null;
}

export interface Opportunity {
  appl_no: string;
  ingredient: string;
  trade_name?: string | null;
  applicant?: string | null;
  patent_number: string;
  expiration_date?: string | null;
  months_to_expiry?: number | null;
  opportunity_score: number;
  band: string;
  rationale: string;
}

export interface OpportunitySummary {
  total: number;
  by_band: Record<string, number>;
  top: Opportunity[];
  sponsor_leaderboard: Array<{ sponsor: string; score: number }>;
}

export interface AlertSubscription {
  id: string;
  user_email: string;
  name?: string | null;
  modules: string[];
  sponsors: string[];
  drugs: string[];
  patents: string[];
  therapy_areas: string[];
  min_priority: number;
  channels: string[];
  is_active: boolean;
  created_at: string;
}
