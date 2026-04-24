# models.py

from sqlalchemy import Column, Integer, String, Float, Text, DateTime
from datetime import datetime
from app.database.db import Base


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id                = Column(Integer, primary_key=True, index=True)
    text              = Column(Text,    nullable=False)
    source_domain     = Column(String,  nullable=True,  index=True)
    verdict           = Column(String,  nullable=False)
    confidence        = Column(Integer, nullable=False)
    credibility_score = Column(Integer, nullable=False)
    sentiment         = Column(String,  nullable=False)
    fake_probability  = Column(Float,   nullable=False)
    risk_score        = Column(Float,   nullable=False)
    risk_level        = Column(String,  nullable=False)
    created_at        = Column(DateTime, default=datetime.utcnow)


class DomainCache(Base):
    """
    Caches WHOIS/domain-analysis results for unknown domains.

    The static source database (Python dict in source_analyzer.py) covers
    ~80 known domains instantly. For any domain NOT in that dict, a live
    RDAP query is made — which takes 3-5 seconds. This table stores the
    result so the same unknown domain is only queried once ever.
    Subsequent requests for the same domain are served in milliseconds.

    Cache entries do not expire automatically. To refresh a stale entry,
    delete its row:  DELETE FROM domain_cache WHERE domain = 'example.com';
    """
    __tablename__ = "domain_cache"

    domain          = Column(String,  primary_key=True, index=True)
    credibility     = Column(Integer, nullable=False)
    category        = Column(String,  nullable=False, default="unknown")
    domain_age_days = Column(Integer, nullable=False, default=-1)
    notes           = Column(Text,    nullable=False, default="")
    warning         = Column(Text,    nullable=False, default="")
    cached_at       = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# New tables for the three credibility modules
# ---------------------------------------------------------------------------

class ExternalRating(Base):
    """
    Stores credibility ratings fetched from external APIs (Module 1).
    Updated periodically by external_sync.py.

    These ratings serve as the authoritative external reference and are
    combined with internal signals (Modules 2 & 3) in source_analyzer.py.
    """
    __tablename__ = "external_ratings"

    domain      = Column(String,  primary_key=True, index=True)
    credibility = Column(Integer, nullable=False)
    category    = Column(String,  nullable=False, default="unknown")
    bias        = Column(String,  nullable=False, default="unknown")
    notes       = Column(Text,    nullable=False, default="")
    api_source  = Column(String,  nullable=False, default="mock")  # "MBFC", "NewsGuard", etc.
    fetched_at  = Column(DateTime, default=datetime.utcnow)


class FeedbackLog(Base):
    """
    Logs each run of the feedback engine (Module 2).

    Used for anomaly detection — if article count spikes between runs,
    the domain is skipped to prevent score manipulation.
    """
    __tablename__ = "feedback_log"

    id            = Column(Integer, primary_key=True, index=True)
    domain        = Column(String,  nullable=False, index=True)
    article_count = Column(Integer, nullable=False)
    avg_fake_rate = Column(Float,   nullable=False)
    score_delta   = Column(Integer, nullable=False)
    reason        = Column(Text,    nullable=False, default="")
    run_at        = Column(DateTime, default=datetime.utcnow)


class CitationLog(Base):
    """
    Logs each citation boost applied by the citation graph (Module 3).

    Provides an audit trail of why a domain's credibility increased,
    and prevents runaway score inflation across multiple runs.
    """
    __tablename__ = "citation_log"

    id        = Column(Integer, primary_key=True, index=True)
    domain    = Column(String,  nullable=False, index=True)
    raw_boost = Column(Float,   nullable=False)
    boost     = Column(Integer, nullable=False)
    old_score = Column(Integer, nullable=False)
    new_score = Column(Integer, nullable=False)
    reason    = Column(Text,    nullable=False, default="")
    run_at    = Column(DateTime, default=datetime.utcnow)