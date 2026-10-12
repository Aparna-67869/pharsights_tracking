"""Knowledge graph construction and traversal.

Nodes: drug, patent, nda, anda, sponsor, active_moiety, orange_book_record,
       clinical_trial (reserved for future sources).

Edges: has_nda, has_anda, has_patent, marketed_by, has_active_moiety, has_pte,
       paragraph_iv_on, listed_in_orange_book, has_exclusivity, same_family,
       in_litigation, tested_in.

The graph is materialised into ``kg_nodes`` / ``kg_edges`` so traversal is a
handful of indexed queries rather than a fan-out across every fact table. It is
rebuilt idempotently from the canonical entities.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models import (
    ActiveMoiety,
    Drug,
    FtfRecord,
    KgEdge,
    KgNode,
    OrangeBookExclusivity,
    OrangeBookPatent,
    OrangeBookProduct,
    Patent,
    PteApplication,
    PteCertificate,
    Sponsor,
)

log = get_logger(__name__)

NODE_DRUG = "drug"
NODE_PATENT = "patent"
NODE_NDA = "nda"
NODE_ANDA = "anda"
NODE_SPONSOR = "sponsor"
NODE_MOIETY = "active_moiety"
NODE_OB_RECORD = "orange_book_record"
NODE_FTF = "ftf_record"
NODE_PTE = "pte_certificate"


@dataclass
class GraphBuildStats:
    nodes: int = 0
    edges: int = 0
    by_type: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"nodes": self.nodes, "edges": self.edges, "by_type": self.by_type}


class GraphBuilder:
    def __init__(self, session: Session) -> None:
        self.session = session
        self._nodes: dict[tuple[str, str], KgNode] = {}
        self._edges: set[tuple[str, str, str]] = set()
        self.stats = GraphBuildStats()

    def node(
        self,
        node_type: str,
        natural_key: str,
        label: str,
        *,
        ref_table: str | None = None,
        ref_id: str | None = None,
        properties: dict[str, Any] | None = None,
        importance: float = 50.0,
    ) -> KgNode:
        key = (node_type, natural_key)
        existing = self._nodes.get(key)
        if existing is not None:
            return existing
        node = KgNode(
            node_type=node_type,
            natural_key=natural_key,
            label=label,
            ref_table=ref_table,
            ref_id=ref_id,
            properties=properties or {},
            importance=importance,
        )
        self.session.add(node)
        self.session.flush()
        self._nodes[key] = node
        self.stats.nodes += 1
        self.stats.by_type[node_type] = self.stats.by_type.get(node_type, 0) + 1
        return node

    def edge(
        self,
        source: KgNode,
        target: KgNode,
        relation: str,
        *,
        weight: float = 1.0,
        properties: dict[str, Any] | None = None,
    ) -> None:
        key = (source.id, target.id, relation)
        if key in self._edges:
            return
        self._edges.add(key)
        self.session.add(
            KgEdge(
                source_node_id=source.id,
                target_node_id=target.id,
                relation=relation,
                weight=weight,
                properties=properties or {},
            )
        )
        self.stats.edges += 1


def rebuild_graph(session: Session, *, clear: bool = True) -> GraphBuildStats:
    """Rebuild the entire knowledge graph from canonical entities."""
    if clear:
        session.execute(delete(KgEdge))
        session.execute(delete(KgNode))
        session.flush()

    builder = GraphBuilder(session)

    # --- Sponsors ---
    sponsors = {s.id: s for s in session.scalars(select(Sponsor))}
    for sponsor in sponsors.values():
        builder.node(
            NODE_SPONSOR,
            sponsor.normalized_name,
            sponsor.name,
            ref_table="sponsors",
            ref_id=sponsor.id,
            properties={"type": sponsor.sponsor_type},
            importance=sponsor.importance_score,
        )

    # --- Drugs + NDA/ANDA nodes ---
    drugs = list(session.scalars(select(Drug)))
    drug_nodes: dict[str, KgNode] = {}
    for drug in drugs:
        node = builder.node(
            NODE_DRUG,
            drug.normalized_name,
            drug.name,
            ref_table="drugs",
            ref_id=drug.id,
            properties={
                "ingredient": drug.ingredient,
                "therapy_area": drug.therapy_area,
                "rld_nda": drug.rld_nda,
            },
        )
        drug_nodes[drug.id] = node
        if drug.sponsor_id and drug.sponsor_id in sponsors:
            sponsor = sponsors[drug.sponsor_id]
            sponsor_node = builder.node(
                NODE_SPONSOR, sponsor.normalized_name, sponsor.name, ref_table="sponsors", ref_id=sponsor.id
            )
            builder.edge(node, sponsor_node, "marketed_by")

    # --- Patents ---
    patents = list(session.scalars(select(Patent)))
    patent_nodes: dict[str, KgNode] = {}
    for patent in patents:
        node = builder.node(
            NODE_PATENT,
            patent.normalized_number,
            f"US{patent.patent_number}" if not patent.patent_number.upper().startswith(("RE", "US")) else patent.patent_number,
            ref_table="patents",
            ref_id=patent.id,
            properties={
                "expiration_date": patent.expiration_date.isoformat() if patent.expiration_date else None,
                "has_pte": patent.has_pte,
                "has_paragraph_iv": patent.has_paragraph_iv,
                "assignee": patent.assignee,
            },
        )
        patent_nodes[patent.id] = node

    # --- Orange Book products: drug -> NDA/ANDA + patent/exclusivity ---
    products = list(session.scalars(select(OrangeBookProduct).where(OrangeBookProduct.is_active.is_(True))))
    product_to_drug: dict[str, str] = {}
    appl_to_drug: dict[str, str] = {}
    for product in products:
        if not product.drug_id or product.drug_id not in drug_nodes:
            continue
        product_to_drug[product.id] = product.drug_id
        drug_node = drug_nodes[product.drug_id]
        appl_key = f"{product.appl_type}{product.appl_no}"
        appl_to_drug[appl_key] = product.drug_id
        node_type = NODE_ANDA if (product.appl_type or "").upper() == "A" else NODE_NDA
        application_node = builder.node(
            node_type,
            appl_key,
            f"{product.appl_type}{product.appl_no} — {product.trade_name or product.ingredient}",
            ref_table="orange_book_products",
            ref_id=product.id,
            properties={"applicant": product.applicant_full_name or product.applicant},
        )
        builder.edge(drug_node, application_node, "has_anda" if node_type == NODE_ANDA else "has_nda")
        if product.sponsor_id and product.sponsor_id in sponsors:
            sponsor = sponsors[product.sponsor_id]
            sponsor_node = builder.node(
                NODE_SPONSOR, sponsor.normalized_name, sponsor.name, ref_table="sponsors", ref_id=sponsor.id
            )
            builder.edge(application_node, sponsor_node, "marketed_by")

    # --- Orange Book patents -> link to drug via application ---
    ob_patents = list(session.scalars(select(OrangeBookPatent).where(OrangeBookPatent.is_active.is_(True))))
    for row in ob_patents:
        appl_key = f"{row.appl_type}{row.appl_no}"
        drug_id = appl_to_drug.get(appl_key)
        if not drug_id or not row.patent_id or row.patent_id not in patent_nodes:
            continue
        drug_node = drug_nodes[drug_id]
        patent_node = patent_nodes[row.patent_id]
        builder.edge(
            drug_node,
            patent_node,
            "has_patent",
            properties={
                "expiration": row.expiration_date.isoformat() if row.expiration_date else None,
                "use_code": row.patent_use_code,
            },
        )
        if row.delist_flag:
            builder.edge(patent_node, drug_node, "delisted_from", properties={"appl": appl_key})

    # --- FTF: drug -> patent paragraph_iv_on ---
    ftf_rows = list(session.scalars(select(FtfRecord).where(FtfRecord.is_active.is_(True))))
    for row in ftf_rows:
        if row.drug_id and row.drug_id in drug_nodes:
            drug_node = drug_nodes[row.drug_id]
            ftf_node = builder.node(
                NODE_FTF,
                row.source_key,
                f"PIV {row.drug_name} ({row.rld_nda or row.nda_number or 'n/a'})",
                ref_table="ftf_records",
                ref_id=row.id,
                properties={
                    "submission_date": row.date_of_submission.isoformat() if row.date_of_submission else None,
                    "status": row.exclusivity_status,
                },
            )
            builder.edge(drug_node, ftf_node, "has_paragraph_iv")
            if row.patent_id and row.patent_id in patent_nodes:
                builder.edge(drug_node, patent_nodes[row.patent_id], "paragraph_iv_on")

    # --- PTE applications/certificates ---
    pte_apps = list(session.scalars(select(PteApplication).where(PteApplication.is_active.is_(True))))
    for row in pte_apps:
        if row.patent_id and row.patent_id in patent_nodes:
            patent_node = patent_nodes[row.patent_id]
            pte_node = builder.node(
                "pte_application",
                row.source_key,
                f"PTE app {row.application_number}",
                ref_table="pte_applications",
                ref_id=row.id,
                properties={"filing_date": row.filing_date.isoformat() if row.filing_date else None},
            )
            builder.edge(patent_node, pte_node, "has_pte_application")
            if row.drug_id and row.drug_id in drug_nodes:
                builder.edge(drug_nodes[row.drug_id], pte_node, "has_pte_application")

    pte_certs = list(session.scalars(select(PteCertificate).where(PteCertificate.is_active.is_(True))))
    for row in pte_certs:
        if row.patent_id and row.patent_id in patent_nodes:
            patent_node = patent_nodes[row.patent_id]
            cert_node = builder.node(
                NODE_PTE,
                row.source_key,
                f"PTE cert {row.patent_number} (+{row.extension_days or '?'}d)",
                ref_table="pte_certificates",
                ref_id=row.id,
                properties={"extension_days": row.extension_days},
            )
            builder.edge(patent_node, cert_node, "has_pte")
            if row.drug_id and row.drug_id in drug_nodes:
                builder.edge(drug_nodes[row.drug_id], cert_node, "has_pte")

    # --- Active moieties ---
    moieties = list(session.scalars(select(ActiveMoiety).where(ActiveMoiety.is_active.is_(True))))
    for row in moieties:
        moiety_node = builder.node(
            NODE_MOIETY,
            row.normalized_name,
            row.moiety_name,
            ref_table="active_moieties",
            ref_id=row.id,
            properties={
                "sponsor": row.sponsor_name,
                "date_issued": row.date_issued.isoformat() if row.date_issued else None,
            },
        )
        if row.drug_id and row.drug_id in drug_nodes:
            builder.edge(drug_nodes[row.drug_id], moiety_node, "has_active_moiety")
        if row.sponsor_id and row.sponsor_id in sponsors:
            sponsor = sponsors[row.sponsor_id]
            builder.edge(
                moiety_node,
                builder.node(
                    NODE_SPONSOR, sponsor.normalized_name, sponsor.name, ref_table="sponsors", ref_id=sponsor.id
                ),
                "sponsored_by",
            )

    # --- Orange Book exclusivity ---
    exclusivities = list(
        session.scalars(select(OrangeBookExclusivity).where(OrangeBookExclusivity.is_active.is_(True)))
    )
    for row in exclusivities:
        appl_key = f"{row.appl_type}{row.appl_no}"
        drug_id = appl_to_drug.get(appl_key)
        if not drug_id:
            continue
        excl_node = builder.node(
            NODE_OB_RECORD,
            row.source_key,
            f"Exclusivity {row.exclusivity_code}",
            ref_table="orange_book_exclusivity",
            ref_id=row.id,
            properties={
                "code": row.exclusivity_code,
                "date": row.exclusivity_date.isoformat() if row.exclusivity_date else None,
            },
        )
        builder.edge(drug_nodes[drug_id], excl_node, "has_exclusivity")

    session.flush()
    log.info("knowledge graph rebuilt: %s", builder.stats.to_dict())
    return builder.stats


# ===========================================================================
# Traversal
# ===========================================================================


@dataclass
class GraphNeighborhood:
    root: dict[str, Any]
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {"root": self.root, "nodes": self.nodes, "edges": self.edges}


def _node_to_dict(node: KgNode) -> dict[str, Any]:
    return {
        "id": node.id,
        "type": node.node_type,
        "key": node.natural_key,
        "label": node.label,
        "ref_table": node.ref_table,
        "ref_id": node.ref_id,
        "properties": node.properties or {},
        "importance": node.importance,
    }


def neighborhood(
    session: Session,
    *,
    node_type: str,
    natural_key: str,
    depth: int = 1,
    max_nodes: int = 200,
) -> GraphNeighborhood | None:
    """Breadth-first neighbourhood around a node, traversed in both directions."""
    root = session.scalars(
        select(KgNode).where(KgNode.node_type == node_type, KgNode.natural_key == natural_key)
    ).first()
    if root is None:
        return None

    visited: dict[str, KgNode] = {root.id: root}
    edges: list[dict[str, Any]] = []
    seen_edges: set[str] = set()
    queue: deque[tuple[str, int]] = deque([(root.id, 0)])

    while queue and len(visited) < max_nodes:
        current_id, level = queue.popleft()
        if level >= depth:
            continue
        outgoing = list(
            session.scalars(select(KgEdge).where(KgEdge.source_node_id == current_id))
        )
        incoming = list(
            session.scalars(select(KgEdge).where(KgEdge.target_node_id == current_id))
        )
        for edge in outgoing + incoming:
            if edge.id in seen_edges:
                continue
            seen_edges.add(edge.id)
            other_id = edge.target_node_id if edge.source_node_id == current_id else edge.source_node_id
            other = session.get(KgNode, other_id)
            if other is None:
                continue
            edges.append(
                {
                    "id": edge.id,
                    "source": edge.source_node_id,
                    "target": edge.target_node_id,
                    "relation": edge.relation,
                    "weight": edge.weight,
                    "properties": edge.properties or {},
                }
            )
            if other.id not in visited:
                visited[other.id] = other
                queue.append((other.id, level + 1))

    return GraphNeighborhood(
        root=_node_to_dict(root),
        nodes=[_node_to_dict(n) for n in visited.values()],
        edges=edges,
    )


def graph_stats(session: Session) -> dict[str, Any]:
    from sqlalchemy import func

    by_type = dict(
        session.execute(
            select(KgNode.node_type, func.count(KgNode.id)).group_by(KgNode.node_type)
        ).all()
    )
    by_relation = dict(
        session.execute(
            select(KgEdge.relation, func.count(KgEdge.id)).group_by(KgEdge.relation)
        ).all()
    )
    return {
        "node_count": sum(by_type.values()),
        "edge_count": sum(by_relation.values()),
        "nodes_by_type": by_type,
        "edges_by_relation": by_relation,
    }
