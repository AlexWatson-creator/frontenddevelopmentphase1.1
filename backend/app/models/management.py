"""SQLAlchemy ORM models for the management schema (READ-WRITE).

management.project_meta is the single source of truth for project-level
metadata. Each row corresponds to a unique project Number. Multiple
dbo.Project rows (files) can share the same project_number.

Auto-synced: an AFTER INSERT trigger on dbo.Project creates a project_meta
row whenever a new Number appears.
"""
from sqlalchemy import Boolean, Column, Integer, String, Unicode
from sqlalchemy.dialects.mssql import DATETIME2

from app.models.dbo import Base


class ProjectMeta(Base):
    __tablename__ = "project_meta"
    __table_args__ = {"schema": "management"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_number = Column(String(50), nullable=False, unique=True)
    address = Column(String(255))
    job_name = Column(Unicode(255), nullable=True)
    designer = Column(Unicode(100), nullable=True)
    created_at = Column(DATETIME2, nullable=False, server_default="getutcdate()")
    updated_at = Column(DATETIME2, nullable=False, server_default="getutcdate()")



class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "management"}

    id             = Column(Integer, primary_key=True, autoincrement=True)
    email          = Column(String(255), nullable=False, unique=True)
    first_name     = Column(String(100), nullable=False)
    last_name      = Column(String(100), nullable=False)
    password_hash  = Column(String(255), nullable=False)
    role           = Column(String(30), nullable=False, default="STRUCTURAL DESIGNER")
    is_banned      = Column(Boolean, nullable=False, default=False)
    created_at     = Column(DATETIME2, nullable=False, server_default="getutcdate()")