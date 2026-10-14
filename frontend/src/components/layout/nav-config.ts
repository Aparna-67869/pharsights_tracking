import {
  BarChart3,
  BellRing,
  Brain,
  BrainCircuit,
  Building2,
  CalendarClock,
  Database,
  FileSearch,
  FlaskConical,
  GitCompareArrows,
  LayoutDashboard,
  Network,
  Search,
  ShieldCheck,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  group: string;
  scope?: string;
  badge?: "alerts";
  hint?: string;
}

/**
 * Left-navigation model. Groups mirror the mental model of a regulatory
 * intelligence desk: an overview block, the per-source modules, the analysis
 * tools, and operations/admin.
 */
export const NAV: NavItem[] = [
  { href: "/", label: "Command Center", icon: LayoutDashboard, group: "Overview", hint: "Live executive home" },
  { href: "/executive", label: "Executive View", icon: BarChart3, group: "Overview", scope: "read:data", hint: "30-second landscape" },
  { href: "/alerts", label: "Alerts", icon: BellRing, group: "Overview", badge: "alerts", scope: "read:data", hint: "Priority-scored queue" },

  { href: "/ftf", label: "FTF Intelligence", icon: GitCompareArrows, group: "Regulatory", scope: "read:data", hint: "Paragraph IV certifications" },
  { href: "/pte", label: "PTE Intelligence", icon: CalendarClock, group: "Regulatory", scope: "read:data", hint: "Patent term extensions" },
  { href: "/pde", label: "PDE Intelligence", icon: FlaskConical, group: "Regulatory", scope: "read:data", hint: "Approved active moieties" },
  { href: "/orange-book", label: "Orange Book", icon: Database, group: "Regulatory", scope: "read:data", hint: "Products, patents, supplements" },
  { href: "/patents", label: "Patent Intelligence", icon: ShieldCheck, group: "Regulatory", scope: "read:data", hint: "Expiry runway & listings" },

  { href: "/search", label: "Intelligence Search", icon: Search, group: "Analysis", scope: "read:data", hint: "One box, every entity" },
  { href: "/graph", label: "Knowledge Graph", icon: Network, group: "Analysis", scope: "read:data", hint: "Explore relationships" },
  { href: "/intelligence", label: "Intelligence", icon: Brain, group: "Analysis", scope: "read:data", hint: "AI impact analyses" },
  { href: "/copilot", label: "AI Copilot", icon: BrainCircuit, group: "Analysis", scope: "use:copilot", hint: "Ask the platform" },

  { href: "/sources", label: "Sources & Pipeline", icon: FileSearch, group: "Operations", scope: "read:data", hint: "Collectors and runs" },
];

export const NAV_GROUPS = ["Overview", "Regulatory", "Analysis", "Operations"] as const;

export type { LucideIcon };
export { Building2 };
