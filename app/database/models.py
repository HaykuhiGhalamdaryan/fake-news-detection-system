# models.py

from sqlalchemy import Column, Integer, String, Float, Text, DateTime
from datetime import datetime
from app.database.db import Base


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id                = Column(Integer, primary_key=True, index=True)
    text              = Column(Text,    nullable=False)
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