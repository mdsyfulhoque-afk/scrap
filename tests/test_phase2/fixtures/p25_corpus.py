"""P2.5 acceptance corpus and ground truth with predictable trigram Jaccard similarities."""

from __future__ import annotations


def generate_corpus():
    """Return exactly 100 deterministic documents for dedup acceptance testing."""
    corpus = []

    # Exact duplicates: 10 pairs = 20 docs
    # 10 unique texts to avoid accidental cross-grouping via identical text.
    exact_texts = [
        "The quick brown fox jumps over the lazy dog",
        "Artificial intelligence transforms modern software development",
        "Data quality determines AI model performance",
        "Open source projects accelerate innovation",
        "Python remains the dominant language for data science",
        "Cloud computing delivers scalable infrastructure for applications",
        "Cybersecurity protects networks from malicious attacks",
        "DevOps practices streamline software delivery pipelines",
        "Blockchain enables decentralized trust in financial systems",
        "Internet of things connects devices to digital networks",
    ]
    for i in range(10):
        text = exact_texts[i]
        corpus.append({
            "id": f"exact_{i}_a",
            "text": text,
            "source_url": f"https://example.com/exact/{i}/a",
            "category": "exact_duplicate",
            "quality_score": 0.9,
            "warning_count": 0,
            "expected_group_id": f"exact_group_{i}",
        })
        corpus.append({
            "id": f"exact_{i}_b",
            "text": text,
            "source_url": f"https://example.com/exact/{i}/b",
            "category": "exact_duplicate",
            "quality_score": 0.9,
            "warning_count": 0,
            "expected_group_id": f"exact_group_{i}",
        })

    # Normalized duplicates: 10 pairs = 20 docs
    # 10 unique texts; pair member b differs only in lowercase and extra spaces.
    normalized_texts = [
        "Machine learning algorithms improve predictive accuracy",
        "Deep learning powers computer vision applications",
        "Natural language processing enables text understanding",
        "Quantum computing promises exponential speedups",
        "Renewable energy reduces carbon emissions globally",
        "Autonomous vehicles use sensors for safe navigation",
        "Gene editing allows precise DNA modifications",
        "Virtual reality creates immersive digital experiences",
        "3D printing manufactures objects from digital models",
        "Nanotechnology manipulates materials at atomic scale",
    ]
    for i in range(10):
        text = normalized_texts[i]
        corpus.append({
            "id": f"norm_{i}_a",
            "text": text,
            "source_url": f"https://example.com/norm/{i}/a",
            "category": "normalized_duplicate",
            "quality_score": 0.9,
            "warning_count": 0,
            "expected_group_id": f"norm_group_{i}",
        })
        corpus.append({
            "id": f"norm_{i}_b",
            "text": text.lower().replace(" ", "  "),
            "source_url": f"https://example.com/norm/{i}/b",
            "category": "normalized_duplicate",
            "quality_score": 0.9,
            "warning_count": 0,
            "expected_group_id": f"norm_group_{i}",
        })

    # Near duplicates: 10 pairs = 20 docs
    # Each pair uses a distinct base text with a single-word substitution.
    near_bases = [
        "The quick brown fox jumps over the lazy dog. This is a comprehensive document containing many trigrams for predictable similarity calculations during the acceptance test corpus evaluation phase.",
        "Artificial intelligence transforms modern software development practices. Advanced machine learning algorithms improve model accuracy through iterative training on very large datasets.",
        "Data quality determines AI model performance in production environments. Clean and well structured information enables better predictions and more reliable automated decision making systems.",
        "Open source projects accelerate technological innovation globally. Active community contributions drive rapid improvements and widespread adoption of new frameworks and programming languages.",
        "Python remains the dominant language for data science and analysis. Its simple syntax and powerful libraries make it ideal for statistical computing and data visualization tasks.",
        "Cloud computing provides scalable infrastructure for modern applications. Elastic on demand resources reduce operational costs and improve service availability for global enterprise customers.",
        "Cybersecurity protects computer networks from malicious attacks and intrusions. Strong encryption and multi factor authentication safeguard sensitive data both in transit and at rest.",
        "DevOps practices streamline software delivery pipelines and workflows. Continuous integration combined with automated deployment reduce human errors and increase release frequency significantly.",
        "Blockchain technology enables decentralized trust mechanisms in finance. Immutable distributed ledgers support transparent transactions without relying on central authorities or intermediaries.",
        "Internet of things connects physical devices to digital networks. Smart embedded sensors generate real time data for process automation and intelligent monitoring systems.",
    ]
    near_subs = [
        ("predictable", "reliable"),
        ("improve", "enhance"),
        ("structured", "formatted"),
        ("rapid", "fast"),
        ("simple", "clean"),
        ("Elastic", "Flexible"),
        ("safeguard", "protect"),
        ("deployment", "rollout"),
        ("Immutable", "Permanent"),
        ("Smart", "Intelligent"),
    ]
    for i in range(10):
        text_a = near_bases[i]
        text_b = near_bases[i].replace(*near_subs[i])
        corpus.append({
            "id": f"near_{i}_a",
            "text": text_a,
            "source_url": f"https://example.com/near/{i}/a",
            "category": "near_duplicate",
            "quality_score": 0.85,
            "warning_count": 0,
            "expected_group_id": f"near_group_{i}",
        })
        corpus.append({
            "id": f"near_{i}_b",
            "text": text_b,
            "source_url": f"https://example.com/near/{i}/b",
            "category": "near_duplicate",
            "quality_score": 0.85,
            "warning_count": 0,
            "expected_group_id": f"near_group_{i}",
        })

    # Unique documents: 12 docs
    unique_texts = [
        "Blockchain technology enables decentralized finance applications and secure distributed ledger systems",
        "Quantum computing algorithms solve complex optimization and cryptography problems efficiently",
        "Renewable energy from solar and wind power reduces carbon emissions and fights climate change",
        "Autonomous vehicles use sensors and artificial intelligence for safe navigation and driving",
        "Gene editing with CRISPR allows precise modifications to DNA sequences in living organisms",
        "Virtual reality creates immersive digital experiences for gaming education and training",
        "3D printing manufactures physical objects from digital models using additive manufacturing processes",
        "Nanotechnology manipulates materials at atomic scale for medical and industrial applications",
        "Space exploration missions seek to understand the universe and find habitable exoplanets",
        "Synthetic biology designs biological systems for producing fuels chemicals and medicines",
        "Neural networks learn patterns from data for image recognition natural language processing tasks",
        "Internet of things connects physical devices to the internet for smart home and industrial automation",
    ]
    for i in range(12):
        corpus.append({
            "id": f"unique_{i}",
            "text": unique_texts[i],
            "source_url": f"https://example.com/unique/{i}",
            "category": "unique",
            "quality_score": 0.8,
            "warning_count": 0,
            "expected_group_id": None,
        })

    # Similar-topic non-duplicates: 4 pairs = 8 docs (Jaccard < 0.70)
    topic_pairs = [
        (
            "Machine learning enables predictive analytics in business environments with data driven insights",
            "Deep learning powers computer vision applications for autonomous vehicles and robotics",
        ),
        (
            "Quantum computing promises exponential speedups for cryptography and optimization problems",
            "Blockchain technology enables decentralized finance and secure distributed ledger applications",
        ),
        (
            "Renewable energy sources reduce carbon emissions and combat climate change globally",
            "Sustainable agriculture practices improve soil health and food security for growing populations",
        ),
        (
            "Cybersecurity protects networks and data from malicious attacks and unauthorized access",
            "Cloud computing delivers on demand resources and scalable infrastructure for modern applications",
        ),
    ]
    for i, (ta, tb) in enumerate(topic_pairs):
        corpus.append({
            "id": f"topic_{i}_a",
            "text": ta,
            "source_url": f"https://example.com/topic/{i}/a",
            "category": "similar_topic",
            "quality_score": 0.8,
            "warning_count": 0,
            "expected_group_id": None,
        })
        corpus.append({
            "id": f"topic_{i}_b",
            "text": tb,
            "source_url": f"https://example.com/topic/{i}/b",
            "category": "similar_topic",
            "quality_score": 0.8,
            "warning_count": 0,
            "expected_group_id": None,
        })

    # Formatting variations: 2 sets x 3 versions = 6 docs
    # Markup tags create different trigrams, so Jaccard < 0.85 between all pairs.
    fmt_text = "Data governance ensures trustworthy information systems for enterprise applications"
    fmt_html = "<html><body><p>Data governance ensures trustworthy information systems for enterprise applications</p></body></html>"
    fmt_md = "# Data Governance\n\nEnsures trustworthy information systems for enterprise **applications** with proper controls and oversight."
    for i in range(2):
        corpus.append({
            "id": f"fmt_{i}_html",
            "text": fmt_html,
            "source_url": f"https://example.com/fmt/{i}/html",
            "category": "formatting_variation",
            "quality_score": 0.9,
            "warning_count": 0,
            "expected_group_id": None,
        })
        corpus.append({
            "id": f"fmt_{i}_md",
            "text": fmt_md,
            "source_url": f"https://example.com/fmt/{i}/md",
            "category": "formatting_variation",
            "quality_score": 0.9,
            "warning_count": 0,
            "expected_group_id": None,
        })
        corpus.append({
            "id": f"fmt_{i}_txt",
            "text": fmt_text,
            "source_url": f"https://example.com/fmt/{i}/txt",
            "category": "formatting_variation",
            "quality_score": 0.9,
            "warning_count": 0,
            "expected_group_id": None,
        })

    # Transitive chain: 3 docs
    # A~B >= 0.90, B~C < 0.85, A~C < 0.80
    # Note: Jaccard triangle inequality makes B~C >= 0.90 incompatible with A~C < 0.80
    trans_a = (
        "Natural language processing enables text understanding capabilities for analysis of "
        "human communication data across various domains and use cases in modern research "
        "applications and scenarios for testing purposes."
    )
    trans_b = (
        "Natural language processing enables text understanding capabilities for analysis of "
        "human communication data across various domains and use cases in modern research "
        "applications and scenarios for evaluation purposes."
    )
    trans_c = (
        "Computer vision systems enable image recognition and visual pattern analysis for "
        "automated understanding in production environments with high accuracy and reliability."
    )
    corpus.append({
        "id": "trans_a",
        "text": trans_a,
        "source_url": "https://example.com/trans/a",
        "category": "transitive_chain",
        "quality_score": 0.9,
        "warning_count": 0,
        "expected_group_id": "trans_group",
    })
    corpus.append({
        "id": "trans_b",
        "text": trans_b,
        "source_url": "https://example.com/trans/b",
        "category": "transitive_chain",
        "quality_score": 0.9,
        "warning_count": 0,
        "expected_group_id": "trans_group",
    })
    corpus.append({
        "id": "trans_c",
        "text": trans_c,
        "source_url": "https://example.com/trans/c",
        "category": "transitive_chain",
        "quality_score": 0.9,
        "warning_count": 0,
        "expected_group_id": None,
    })

    # Representative competition: 3 docs
    # 2 near-dups with Jaccard >= 0.90, 1 high-quality unique
    rep_a = "Cloud computing provides scalable infrastructure for applications and services in modern enterprises"
    rep_b = "Cloud computing provides scalable infrastructure for applications and services in modern enterprises worldwide"
    rep_c = "Edge computing reduces latency for distributed systems and real time processing"
    corpus.append({
        "id": "rep_a",
        "text": rep_a,
        "source_url": "https://example.com/rep/a",
        "category": "representative_competition",
        "quality_score": 0.6,
        "warning_count": 0,
        "expected_group_id": "rep_group",
    })
    corpus.append({
        "id": "rep_b",
        "text": rep_b,
        "source_url": "https://example.com/rep/b",
        "category": "representative_competition",
        "quality_score": 0.7,
        "warning_count": 0,
        "expected_group_id": "rep_group",
    })
    corpus.append({
        "id": "rep_c",
        "text": rep_c,
        "source_url": "https://example.com/rep/c",
        "category": "representative_competition",
        "quality_score": 0.95,
        "warning_count": 0,
        "expected_group_id": None,
    })

    # Ambiguous threshold: 4 pairs = 8 docs (Jaccard around 0.82-0.88)
    ambiguous_pairs = [
        (
            "Microservices enable independent deployment of components in modern cloud native application architectures",
            "Microservices enable independent deployment in modern cloud native application architectures",
        ),
        (
            "Testing ensures software reliability and correctness through comprehensive validation procedures",
            "Testing ensures software quality and correctness through comprehensive validation procedures",
        ),
        (
            "Version control systems track changes in source code and enable collaboration among developers",
            "Version control systems track changes in source code and enable collaboration among distributed developers",
        ),
        (
            "Continuous integration automates building and testing of code changes in software projects",
            "Continuous integration automates building and testing of code changes in agile software projects and workflows",
        ),
    ]
    for i, (ta, tb) in enumerate(ambiguous_pairs):
        corpus.append({
            "id": f"amb_{i}_a",
            "text": ta,
            "source_url": f"https://example.com/amb/{i}/a",
            "category": "ambiguous_threshold",
            "quality_score": 0.8,
            "warning_count": 0,
            "expected_group_id": None,
        })
        corpus.append({
            "id": f"amb_{i}_b",
            "text": tb,
            "source_url": f"https://example.com/amb/{i}/b",
            "category": "ambiguous_threshold",
            "quality_score": 0.8,
            "warning_count": 0,
            "expected_group_id": None,
        })

    assert len(corpus) == 100, f"Corpus size mismatch: {len(corpus)}"
    return corpus


def get_ground_truth():
    """Return ground truth for dedup evaluation with actual computed Jaccard ranges."""
    corpus = generate_corpus()
    expected_groups = []
    expected_unique = []
    expected_representatives = {}

    seen_groups = {}
    for doc in corpus:
        gid = doc.get("expected_group_id")
        if gid:
            seen_groups.setdefault(gid, []).append(doc["id"])
        else:
            expected_unique.append(doc["id"])

    jaccard_ranges = {
        "exact_group": (1.0, 1.0),
        "norm_group": (1.0, 1.0),
        "near_group_0": (0.9220, 0.9230),
        "near_group_1": (0.9300, 0.9310),
        "near_group_2": (0.9320, 0.9330),
        "near_group_3": (0.9260, 0.9270),
        "near_group_4": (0.9090, 0.9100),
        "near_group_5": (0.9160, 0.9170),
        "near_group_6": (0.9160, 0.9170),
        "near_group_7": (0.9000, 0.9010),
        "near_group_8": (0.9030, 0.9040),
        "near_group_9": (0.9560, 0.9570),
        "trans_group": (0.9260, 0.9270),
        "rep_group": (0.9230, 0.9240),
    }

    for gid, members in seen_groups.items():
        jmin, jmax = jaccard_ranges.get(gid, (0.0, 1.0))
        expected_groups.append({
            "group_id": gid,
            "document_ids": sorted(members),
            "similarity_type": (
                "exact" if gid.startswith("exact") else
                "normalized" if gid.startswith("norm") else
                "near" if gid.startswith("near") or gid == "trans_group" else
                "representative"
            ),
            "expected_jaccard_range": (jmin, jmax),
        })
        rep = min(
            members,
            key=lambda mid: (
                0 if next(d["quality_score"] for d in corpus if d["id"] == mid) == 0 else
                -next(d["quality_score"] for d in corpus if d["id"] == mid),
                next(d["warning_count"] for d in corpus if d["id"] == mid),
                mid,
            )
        )
        expected_representatives[gid] = rep

    return {
        "expected_groups": expected_groups,
        "expected_unique": sorted(expected_unique),
        "expected_representatives": expected_representatives,
        "transitive_chain_docs": ["trans_a", "trans_b", "trans_c"],
    }
