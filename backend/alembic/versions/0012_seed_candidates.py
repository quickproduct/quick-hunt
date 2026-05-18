"""Seed candidates for admin user

Revision ID: 0012
Revises: 0011
Create Date: 2026-04-06 00:00:00.000000

Creates two candidate profiles for the admin tenant:
  - Suraj Shetty
  - Gunjan Pandey
"""
from alembic import op
from sqlalchemy import text
import json

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

# Admin tenant ID (from 0007 migration)
ADMIN_TENANT_ID = "00000000-0000-0000-0000-000000000001"

# R2 bucket resume URLs - update these with your actual R2 public URL
# Format: https://<account_id>.r2.cloudflarestorage.com/job-automation/<filename>
# Or if using custom domain: https://your-domain.com/job-automation/<filename>
R2_BASE_URL = "https://pub-8c0ae864a440df58cc57899a1e37d71f.r2.dev/job-automation"

CANDIDATES = [
    {
        "id": "00000000-0000-0000-0000-000000000010",
        "name": "Suraj Shetty",
        "email": "shetty44444@gmail.com",
        "title": "PHP Senior Backend Engineer",
        "skills": [
            "PHP", "Laravel", "Python", "FastAPI", "React", "Docker", "Kubernetes",
            "RabbitMQ", "Kafka", "PostgreSQL", "MongoDB", "Redis", "GenAI",
            "LangChain", "LangGraph", "Ollama", "Groq API",
            "Vector Databases (pgvector, Typesense)", "AWS (S3, EC2)",
            "System Design", "Microservices Architecture"
        ],
        "years_experience": 5,
        "bio": "Results-driven backend engineer with 5+ years of experience building scalable, high-performance systems. Strong expertise in Laravel, FastAPI, with hands-on experience in GenAI, RAG systems, and cloud-native architectures. Passionate about clean code, system design, and production-ready solutions.",
        "target_roles": [
            "PHP Senior Backend Engineer",
            "PHP Backend Engineer",
            "PHP Laravel Developer",
            "PHP Backend Developer"
        ],
        "target_locations": ["India", "Bangalore", "Remote", "Mumbai", "Hyderabad", "Pune", "Chennai", "Delhi", "Gurgaon", "Noida"],
        "resume_url": f"{R2_BASE_URL}/suraj-shetty-software-engineer.pdf",
        "cover_letter_template": """Dear Hiring Manager,

I am excited to apply for the {job-title} role at {company-name}. I am a backend software engineer with experience in Laravel, Python/FastAPI, React, MySQL, MongoDB, Redis, RabbitMQ, Kafka, Docker, Kubernetes, and AWS, and I have worked on scalable systems in healthcare, payments, logistics, and SaaS.

In my recent roles, I have handled backend development, API integrations, performance optimization, queue-based processing, and microservices architecture. I have also built AI-powered projects using LangChain, LangGraph, ChromaDB, and GroqAI, which strengthened my ability to work on modern, production-oriented applications.

I would be glad to bring my experience and problem-solving approach to {company-name}. Thank you for your time and consideration.

Sincerely,
Suraj Shetty"""
    },
    {
        "id": "00000000-0000-0000-0000-000000000011",
        "name": "Gunjan Pandey",
        "email": "gunjanap2018@gmail.com",
        "title": "PHP Senior Backend Engineer",
        "skills": [
            "PHP", "Laravel", "Python", "FastAPI", "React", "Docker", "Kubernetes",
            "RabbitMQ", "Kafka", "PostgreSQL", "MongoDB", "Redis", "GenAI",
            "LangChain", "LangGraph", "Ollama", "Groq API",
            "Vector Databases (pgvector, Typesense)", "AWS (S3, EC2)",
            "System Design", "Microservices Architecture"
        ],
        "years_experience": 5,
        "bio": "Results-driven backend engineer with 5+ years of experience building scalable, high-performance systems. Strong expertise in Laravel, FastAPI, with hands-on experience in GenAI, RAG systems, and cloud-native architectures. Passionate about clean code, system design, and production-ready solutions.",
        "target_roles": [
            "PHP Senior Backend Engineer",
            "PHP Backend Engineer",
            "PHP Laravel Developer",
            "PHP Backend Developer"
        ],
        "target_locations": ["India", "Bangalore", "Remote", "Mumbai", "Hyderabad", "Pune", "Chennai", "Delhi", "Gurgaon", "Noida"],
        "resume_url": f"{R2_BASE_URL}/gunjan-pandey-software-engineer.pdf",
        "cover_letter_template": """Dear Hiring Manager,

I am excited to apply for the {job-title} role at {company-name}. I am a backend software engineer with experience in PHP, Python, Laravel, FastAPI, ReactJS, MySQL, MongoDB, Redis, RabbitMQ, Docker, Kubernetes, and AWS, and I have worked on scalable systems in crowdfunding, travel booking, logistics, and SaaS.

In my recent roles, I have handled backend development, API integrations, payment gateway integrations, performance optimization, and microservices architecture. I have also worked on security improvements and built AI-powered projects using LangChain, LangGraph, ChromaDB, and GroqAI, strengthening my ability to develop modern, production-ready applications.

I would be glad to bring my experience and problem-solving approach to {company-name}. Thank you for your time and consideration.

Sincerely,
Gunjan Pandey"""
    }
]


def upgrade() -> None:
    conn = op.get_bind()

    # Check if admin tenant exists
    result = conn.execute(
        text("SELECT id FROM tenants WHERE id = :id"),
        {"id": ADMIN_TENANT_ID}
    ).fetchone()

    if not result:
        print(f"\n⚠ Admin tenant not found. Run 0007 migration first.\n")
        return

    created = []
    skipped = []

    for candidate in CANDIDATES:
        # Check if candidate already exists
        result = conn.execute(
            text("SELECT id FROM candidates WHERE email = :email AND tenant_id = :tenant_id"),
            {"email": candidate["email"], "tenant_id": ADMIN_TENANT_ID}
        ).fetchone()

        if result:
            skipped.append(candidate["name"])
            continue

        # Insert candidate using to_jsonb for arrays
        conn.execute(
            text("""
                INSERT INTO candidates (
                    id, tenant_id, name, email, skills, years_experience,
                    target_roles, target_locations, bio, resume_url, cover_letter_template, is_active
                )
                VALUES (
                    :id, :tenant_id, :name, :email, (:skills)::jsonb, :years_experience,
                    (:target_roles)::jsonb, (:target_locations)::jsonb, :bio, :resume_url, :cover_letter_template, true
                )
            """),
            {
                "id": candidate["id"],
                "tenant_id": ADMIN_TENANT_ID,
                "name": candidate["name"],
                "email": candidate["email"],
                "skills": json.dumps(candidate["skills"]),
                "years_experience": candidate["years_experience"],
                "target_roles": json.dumps(candidate["target_roles"]),
                "target_locations": json.dumps(candidate["target_locations"]),
                "bio": candidate["bio"],
                "resume_url": candidate.get("resume_url"),
                "cover_letter_template": candidate["cover_letter_template"],
            }
        )
        created.append(candidate["name"])

    if created:
        print(f"\n✓ Candidates created: {', '.join(created)}")
        print(f"  Tenant ID: {ADMIN_TENANT_ID}\n")
    if skipped:
        print(f"\nℹ Candidates already exist: {', '.join(skipped)}\n")


def downgrade() -> None:
    conn = op.get_bind()

    emails = [c["email"] for c in CANDIDATES]
    conn.execute(
        text("DELETE FROM candidates WHERE email = ANY(:emails) AND tenant_id = :tenant_id"),
        {"emails": emails, "tenant_id": ADMIN_TENANT_ID}
    )

    print(f"\n✓ Candidates removed: {', '.join([c['name'] for c in CANDIDATES])}\n")
