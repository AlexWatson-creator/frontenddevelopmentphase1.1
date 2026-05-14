"""Quick connection test — verifies ORM models map to the live JAPBIMDB."""
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Project, Level, DboColumn, Wall, Floor, Beam, Foundation


def test_connection_and_project_count():
    engine = create_engine(settings.DATABASE_URL)
    with Session(engine) as db:
        count = db.query(Project).count()
        assert count >= 1, f"Expected at least 1 project, got {count}"


def test_element_counts_for_first_project():
    engine = create_engine(settings.DATABASE_URL)
    with Session(engine) as db:
        project = db.query(Project).first()
        assert project is not None

        levels = db.query(Level).filter(Level.Project_id == project.Id).count()
        columns = db.query(DboColumn).filter(DboColumn.Project_id == project.Id).count()
        walls = db.query(Wall).filter(Wall.Project_id == project.Id).count()
        floors = db.query(Floor).filter(Floor.Project_id == project.Id).count()
        beams = db.query(Beam).filter(Beam.Project_id == project.Id).count()
        foundations = db.query(Foundation).filter(Foundation.Project_id == project.Id).count()

        # At least some element tables should have data
        total = columns + walls + floors + beams + foundations
        assert total > 0, f"Expected elements for project {project.Id}, got 0"
        print(f"\nProject {project.Id} ({project.FileName}):")
        print(f"  Levels={levels} Columns={columns} Walls={walls} "
              f"Floors={floors} Beams={beams} Foundations={foundations}")
