"""Generate a reproducible, explicitly synthetic job-search evaluation dataset."""

import argparse
import csv
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from backend.app.config import PROJECT_ROOT

ROLES = [
    ("Artificial Intelligence", "AI Engineer Intern",
     ["Python", "LLM", "RAG", "FastAPI"],
     "Prototype retrieval-augmented assistants and evaluate language-model outputs."),
    ("Generative AI", "Generative AI Intern",
     ["Python", "Generative AI", "LLM", "Prompt Engineering"],
     "Build grounded text-generation workflows and measure answer quality."),
    ("Machine Learning", "Machine Learning Intern",
     ["Python", "scikit-learn", "Machine Learning", "Pandas"],
     "Prepare datasets, train baseline models, and document offline experiments."),
    ("Data Science", "Data Science Intern",
     ["Python", "SQL", "Data Analysis", "Pandas"],
     "Analyze structured datasets and communicate reproducible findings."),
    ("Natural Language Processing", "NLP Engineer Intern",
     ["Python", "NLP", "Transformers", "PyTorch"],
     "Develop text classification and information-extraction prototypes."),
    ("Backend Engineering", "Python Backend Intern",
     ["Python", "FastAPI", "SQL", "Docker"],
     "Implement typed APIs, database operations, and automated tests."),
    ("Data Engineering", "Data Engineering Intern",
     ["Python", "SQL", "ETL", "Docker"],
     "Build validated batch pipelines and monitor data quality."),
    ("Search and Retrieval", "Search Engineer Intern",
     ["Python", "FAISS", "RAG", "Information Retrieval"],
     "Evaluate ranking methods and improve retrieval relevance."),
    ("Computer Vision", "Computer Vision Intern",
     ["Python", "PyTorch", "Deep Learning", "OpenCV"],
     "Create CPU-friendly image-processing experiments and benchmarks."),
    ("Cloud Engineering", "Cloud Software Intern",
     ["Python", "AWS", "Docker", "Kubernetes"],
     "Automate deployable services and document operational checks."),
    ("Frontend Engineering", "Frontend Developer Intern",
     ["JavaScript", "TypeScript", "React", "API Integration"],
     "Build accessible interfaces for data-heavy product workflows."),
    ("Product Analytics", "Product Data Analyst Intern",
     ["SQL", "Python", "Data Analysis", "Experimentation"],
     "Measure product usage with clearly defined and reproducible metrics."),
]
LOCATIONS = [
    "Remote - India", "Bengaluru, India", "Hyderabad, India", "Pune, India",
    "Chennai, India", "Mumbai, India", "Delhi NCR, India", "Remote - India",
    "Kochi, India", "Noida, India",
]
EMPLOYMENT = ["Internship", "Internship", "Full-time", "Contract", "Part-time"]


def generate_rows() -> list[dict[str, str | int]]:
    rows = []
    for role_index, (category, title, skills, task) in enumerate(ROLES):
        for variant in range(10):
            number = role_index * 10 + variant + 1
            level = "Internship" if variant < 7 else ("Entry-level" if variant < 9 else "Junior")
            employment = EMPLOYMENT[variant % len(EMPLOYMENT)]
            location = LOCATIONS[(role_index + variant) % len(LOCATIONS)]
            company = f"Example Labs {number:03d}"
            rows.append({
                "external_id": f"synthetic-{number:03d}",
                "title": title if variant < 4 else f"{title} - Cohort {variant - 2}",
                "company": company,
                "location": location,
                "description": (
                    "SYNTHETIC DEMO LISTING — not a real vacancy. "
                    f"{company} is a fictional portfolio-data organization. "
                    f"In this {level.casefold()} project, the selected candidate will {task} "
                    f"Applicants can practice with {', '.join(skills)}. "
                    "This record exists only for local product demonstration and evaluation."
                ),
                "employment_type": employment,
                "experience_level": level,
                "role_category": category,
                "skills": ", ".join(skills),
                "salary_min": None if employment == "Internship" else 600000 + variant * 25000,
                "salary_max": None if employment == "Internship" else 1200000 + variant * 25000,
                "apply_url": "",
                "posted_at": datetime.combine(
                    date(2026, 10, 1) + timedelta(days=number % 30),
                    time(hour=12), tzinfo=timezone.utc,
                ).isoformat(),
                "is_synthetic": "true",
            })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=PROJECT_ROOT / "data" / "raw" / "jobs.csv"
    )
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rows = generate_rows()
    with args.output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} synthetic demo listings to {args.output}")


if __name__ == "__main__":
    main()
