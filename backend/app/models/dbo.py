"""SQLAlchemy ORM models for the dbo schema (READ-ONLY).

WARNING: These tables are synced by Clarity/Dynamo.
NEVER write to dbo tables except these allowed delete operations:
  1. DELETE /api/projects/{number} -> delete all dbo.Project rows for that Number (FK cascades)
  2. DELETE /api/projects/files/{id} -> delete single dbo.Project row (FK cascades)
  3. POST /api/projects/{number}/merge -> reassign design records, then delete source Project

PATCH writes ONLY to management.project_meta, never dbo.
"""
from sqlalchemy import (
    BigInteger,
    Column,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.mssql import REAL, SMALLDATETIME
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------

class Project(Base):
    __tablename__ = "Project"
    __table_args__ = {"schema": "dbo"}

    Id = Column(Integer, primary_key=True, autoincrement=True)
    Number = Column(String(50))
    FileName = Column(String(255))
    FileLocation = Column(String(255))
    Software = Column(String(50))
    Address = Column(String(255))
    LastRunTime = Column(SMALLDATETIME)

    # Relationships to element tables
    levels = relationship("Level", back_populates="project", passive_deletes=True)
    grids = relationship("Grid", back_populates="project", passive_deletes=True)
    columns = relationship("DboColumn", back_populates="project", passive_deletes=True)
    column_types = relationship("ColumnType", back_populates="project", passive_deletes=True)
    walls = relationship("Wall", back_populates="project", passive_deletes=True)
    wall_types = relationship("WallType", back_populates="project", passive_deletes=True)
    floors = relationship("Floor", back_populates="project", passive_deletes=True)
    floor_types = relationship("FloorType", back_populates="project", passive_deletes=True)
    beams = relationship("Beam", back_populates="project", passive_deletes=True)
    beam_types = relationship("BeamType", back_populates="project", passive_deletes=True)
    foundations = relationship("Foundation", back_populates="project", passive_deletes=True)
    foundation_types = relationship("FoundationType", back_populates="project", passive_deletes=True)


# ---------------------------------------------------------------------------
# Levels & Grids
# ---------------------------------------------------------------------------

class Level(Base):
    __tablename__ = "Levels"
    __table_args__ = {"schema": "dbo"}

    id = Column(Integer, primary_key=True)
    Name = Column(String(255))
    Elevation = Column(REAL)
    Project_id = Column(Integer, ForeignKey("dbo.Project.Id", ondelete="CASCADE"), nullable=False)
    StoryHeight = Column(Integer)
    GSA_Revit_m2 = Column(REAL)

    project = relationship("Project", back_populates="levels")


class Grid(Base):
    __tablename__ = "Grids"
    __table_args__ = {"schema": "dbo"}

    id = Column(Integer, primary_key=True)
    Name = Column(String(50))
    StartLocation = Column(Text)
    EndLocation = Column(Text)
    Project_id = Column(Integer, ForeignKey("dbo.Project.Id", ondelete="CASCADE"), nullable=False)

    project = relationship("Project", back_populates="grids")


# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------

class Material(Base):
    __tablename__ = "Material"
    __table_args__ = {"schema": "dbo"}

    id = Column(Integer, primary_key=True)
    Name = Column(String(255))


class SpecialMaterial(Base):
    __tablename__ = "SpecialMaterial"
    __table_args__ = {"schema": "dbo"}

    id = Column(Integer, primary_key=True)
    AirEntrainment = Column(String(50))
    CompressiveStrength = Column(String(50))
    CorrosionInhibitor = Column(String(50))
    ExposureClass = Column(String(50))
    SpecialMixtures = Column(String(50))


# ---------------------------------------------------------------------------
# Columns (composite PK: id + Project_id)
# ---------------------------------------------------------------------------

class ColumnType(Base):
    __tablename__ = "ColumnType"
    __table_args__ = {"schema": "dbo"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    TypeName = Column(String(255))
    eTypeName = Column(String(255))
    D = Column(Integer)
    B = Column(Integer)
    H = Column(Integer)
    Material_id = Column(Integer, ForeignKey("dbo.Material.id"))
    Project_id = Column(Integer, ForeignKey("dbo.Project.Id", ondelete="CASCADE"), nullable=False)

    project = relationship("Project", back_populates="column_types")


class DboColumn(Base):
    """dbo.Columns — named DboColumn to avoid conflict with sqlalchemy.Column."""
    __tablename__ = "Columns"
    __table_args__ = {"schema": "dbo"}

    id = Column(Integer, primary_key=True)
    Project_id = Column(Integer, ForeignKey("dbo.Project.Id", ondelete="CASCADE"), primary_key=True)
    Section_id = Column(Integer, ForeignKey("dbo.ColumnType.id"))
    BaseLocation = Column(Text)
    Toplocation = Column(Text)
    BaseConstraint_id = Column(Integer)
    TopConstraint_id = Column(Integer)
    Mark = Column(String(255))
    Height = Column(Integer)
    Volume = Column(REAL)
    Rotation = Column(SmallInteger)
    Area = Column(REAL)
    SpecialMaterial_id = Column(Integer, ForeignKey("dbo.SpecialMaterial.id"))
    guid = Column(String(50))

    project = relationship("Project", back_populates="columns")


# ---------------------------------------------------------------------------
# Walls (composite PK: id + Project_id)
# ---------------------------------------------------------------------------

class WallType(Base):
    __tablename__ = "WallType"
    __table_args__ = {"schema": "dbo"}

    id = Column(Integer, primary_key=True)
    TypeName = Column(String(255))
    eTypeName = Column(String(255))
    Thickness = Column(Integer)
    Material_id = Column(Integer, ForeignKey("dbo.Material.id"))
    Project_id = Column(Integer, ForeignKey("dbo.Project.Id", ondelete="CASCADE"), nullable=False)

    project = relationship("Project", back_populates="wall_types")


class Wall(Base):
    __tablename__ = "Walls"
    __table_args__ = {"schema": "dbo"}

    id = Column(Integer, primary_key=True)
    Project_id = Column(Integer, ForeignKey("dbo.Project.Id", ondelete="CASCADE"), primary_key=True)
    Section_id = Column(Integer, ForeignKey("dbo.WallType.id"))
    StartLocation = Column(Text)
    Endlocation = Column(Text)
    BaseConstraint_id = Column(Integer)
    TopConstraint_id = Column(Integer)
    Mark = Column(String(255))
    Area = Column(REAL)
    Volume = Column(REAL)
    Height = Column(Integer)
    SideArea = Column(REAL)
    SpecialMaterial_id = Column(Integer, ForeignKey("dbo.SpecialMaterial.id"))
    guid = Column(String(50))

    project = relationship("Project", back_populates="walls")


# ---------------------------------------------------------------------------
# Floors (composite PK: id + Project_id, id is BIGINT)
# ---------------------------------------------------------------------------

class FloorType(Base):
    __tablename__ = "FloorType"
    __table_args__ = {"schema": "dbo"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    TypeName = Column(String(255))
    eTypeName = Column(String(255))
    Thickness = Column(Integer)
    Material_id = Column(Integer, ForeignKey("dbo.Material.id"))
    Project_id = Column(Integer, ForeignKey("dbo.Project.Id", ondelete="CASCADE"), nullable=False)

    project = relationship("Project", back_populates="floor_types")


class Floor(Base):
    __tablename__ = "Floors"
    __table_args__ = {"schema": "dbo"}

    id = Column(BigInteger, primary_key=True)
    Project_id = Column(Integer, ForeignKey("dbo.Project.Id", ondelete="CASCADE"), primary_key=True)
    Section_id = Column(Integer, ForeignKey("dbo.FloorType.id"))
    LocationPoints = Column(Text)
    Level_id = Column(Integer, ForeignKey("dbo.Levels.id"))
    Mark = Column(String(255))
    Perimeter = Column(Integer)
    Area = Column(REAL)
    Volume = Column(REAL)
    SideArea = Column(REAL)
    SpecialMaterial_id = Column(Integer, ForeignKey("dbo.SpecialMaterial.id"))
    guid = Column(String(50))

    project = relationship("Project", back_populates="floors")


# ---------------------------------------------------------------------------
# Beams (composite PK: id + Project_id)
# ---------------------------------------------------------------------------

class BeamType(Base):
    __tablename__ = "BeamType"
    __table_args__ = {"schema": "dbo"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    TypeName = Column(String(255))
    eTypeName = Column(String(255))
    Width = Column(Integer)
    Depth = Column(Integer)
    Material_id = Column(Integer, ForeignKey("dbo.Material.id"))
    Project_id = Column(Integer, ForeignKey("dbo.Project.Id", ondelete="CASCADE"), nullable=False)

    project = relationship("Project", back_populates="beam_types")


class Beam(Base):
    __tablename__ = "Beams"
    __table_args__ = {"schema": "dbo"}

    id = Column(Integer, primary_key=True)
    Project_id = Column(Integer, ForeignKey("dbo.Project.Id", ondelete="CASCADE"), primary_key=True)
    Section_id = Column(Integer, ForeignKey("dbo.BeamType.id"))
    StartLocation = Column(Text)
    EndLocation = Column(Text)
    Level_id = Column(Integer, ForeignKey("dbo.Levels.id"))
    Mark = Column(String(255))
    Length = Column(Integer)
    Volume = Column(REAL)
    Area = Column(REAL)
    SpecialMaterial_id = Column(Integer, ForeignKey("dbo.SpecialMaterial.id"))
    guid = Column(String(50))

    project = relationship("Project", back_populates="beams")


# ---------------------------------------------------------------------------
# Foundations (composite PK: id + Project_id)
# ---------------------------------------------------------------------------

class FoundationType(Base):
    __tablename__ = "FoundationType"
    __table_args__ = {"schema": "dbo"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    TypeName = Column(String(255))
    eTypeName = Column(String(255))
    Material_id = Column(Integer, ForeignKey("dbo.Material.id"))
    Project_id = Column(Integer, ForeignKey("dbo.Project.Id", ondelete="CASCADE"), nullable=False)

    project = relationship("Project", back_populates="foundation_types")


class Foundation(Base):
    __tablename__ = "Foundations"
    __table_args__ = {"schema": "dbo"}

    id = Column(Integer, primary_key=True)
    Project_id = Column(Integer, ForeignKey("dbo.Project.Id", ondelete="CASCADE"), primary_key=True)
    Section_id = Column(Integer, ForeignKey("dbo.FoundationType.id"))
    Level_id = Column(Integer, ForeignKey("dbo.Levels.id"))
    Mark = Column(String(255))
    Area = Column(REAL)
    SideArea = Column(REAL)
    Volume = Column(REAL)
    SpecialMaterial_id = Column(Integer, ForeignKey("dbo.SpecialMaterial.id"))
    guid = Column(String(50))

    project = relationship("Project", back_populates="foundations")
