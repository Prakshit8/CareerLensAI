from types import SimpleNamespace

from backend.app.database.models import CandidateMemory, CandidateProfile, Job
from backend.app.ranking.scorer import score_job
from backend.app.services.ingestion import import_source
from backend.app.services.profiles import update_memory


class InMemorySource:
    source_name = "test"

    def __init__(self, rows):
        self.rows = rows

    def iter_records(self):
        return self.rows


def test_ingestion_is_idempotent_and_skips_invalid_records(db_session):
    source = InMemorySource([
        {"external_id": "job-1", "title": "AI Intern", "company": "Example",
         "skills": "Python,RAG"},
        {"external_id": "job-1", "title": "AI Intern Updated", "company": "Example",
         "skills": "Python,LLM"},
        {"title": "", "company": "Broken"},
    ])
    first = import_source(db_session, source)
    second = import_source(db_session, source)
    assert (first.inserted, first.updated, first.skipped) == (1, 1, 1)
    assert (second.inserted, second.updated, second.skipped) == (0, 2, 1)
    jobs = db_session.query(Job).all()
    assert len(jobs) == 1
    assert jobs[0].title == "AI Intern Updated"


def test_explicit_memory_is_not_replaced_by_inference_and_persists(db_session):
    profile = CandidateProfile(identity="memory-test")
    db_session.add(profile)
    db_session.commit()
    update_memory(
        db_session, profile.id, kind="preference", key="location",
        value="Remote", is_explicit=True,
    )
    db_session.commit()
    update_memory(
        db_session, profile.id, kind="interest", key="location",
        value="On-site", is_explicit=False,
    )
    db_session.commit()
    db_session.expire_all()
    stored = db_session.query(CandidateMemory).one()
    assert stored.value == "Remote"
    assert stored.is_explicit is True


def test_missing_profile_and_salary_data_do_not_receive_perfect_scores():
    profile = SimpleNamespace(
        skills=[], experience_level=None, preferred_roles=[],
        preferred_locations=[], preferred_employment_types=[],
        salary_min=None, salary_max=None, career_interests=None,
    )
    job = SimpleNamespace(
        title="Example role", role_category=None, description="",
        skills=[], experience_level=None, location=None, employment_type=None,
        salary_min=None, salary_max=None,
    )
    scored = score_job(job, profile, {})
    assert scored.score == 0.0
    assert all(value is None for value in scored.components.values())
    assert scored.eligible is None
