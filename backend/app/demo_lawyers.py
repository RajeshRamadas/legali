"""Adds sample lawyers with listed profiles, so the Find a lawyer pages have someone to show in development.

    python -m app.demo_lawyers

The accounts have no password and can't sign in. Re-running updates them in place. Not for production.
"""
from sqlalchemy import select

from .db import SessionLocal
from .models import LawyerProfile, Role, User

WEEKDAYS_10_TO_6 = {d: [["10:00", "13:00"], ["14:30", "18:00"]] for d in ("mon", "tue", "wed", "thu", "fri")}

SAMPLES = [
    {
        "name": "Adv. Ananya Rao", "email": "ananya.rao@example.com",
        "headline": "Property title, RERA and builder disputes", "experience_years": 14, "consultation_fee": 1500,
        "specialisations": ["Property & real estate", "Consumer protection", "Civil disputes"], "languages": ["English", "Kannada", "Telugu"],
        "courts": ["Karnataka High Court", "Karnataka RERA"], "locality": "Jayanagar", "education": "LLB, National Law School of India University",
        "bar_enrolment": "KAR/1102/2011", "weekly_hours": {**WEEKDAYS_10_TO_6, "sat": [["10:00", "13:00"]]},
        "bio": "Ananya advises home buyers on title, khata and EC questions before purchase, and represents buyers against builders for delayed possession before RERA and consumer forums.",
    },
    {
        "name": "Adv. Vikram Shetty", "email": "vikram.shetty@example.com",
        "headline": "Land acquisition and agricultural land conversion", "experience_years": 22, "consultation_fee": 2500,
        "specialisations": ["Property & real estate", "Civil disputes", "Banking & recovery"], "languages": ["English", "Kannada", "Hindi", "Tulu"],
        "courts": ["Karnataka High Court", "City Civil Court, Bengaluru"], "locality": "Rajajinagar", "education": "LLM, Bangalore University",
        "bar_enrolment": "KAR/0451/2003", "weekly_hours": {d: [["16:00", "20:00"]] for d in ("mon", "wed", "fri", "sat")},
        "bio": "Vikram handles land acquisition, DC conversion, partition suits and title litigation for developers and landowners across Bengaluru Rural and Ramanagara.",
    },
    {
        "name": "Adv. Farah Khan", "email": "farah.khan@example.com",
        "headline": "Divorce, custody and family settlements", "experience_years": 9, "consultation_fee": 1200,
        "specialisations": ["Family & divorce", "Wills & succession"], "languages": ["English", "Hindi", "Urdu"],
        "courts": ["Family Court, Bengaluru"], "locality": "Frazer Town", "education": "BA LLB, Christ University",
        "bar_enrolment": "KAR/2290/2016", "weekly_hours": WEEKDAYS_10_TO_6,
        "bio": "Farah works on mutual-consent divorce, maintenance and child custody, and drafts wills and family settlement deeds so property passes without disputes.",
    },
    {
        "name": "Adv. Karthik Iyer", "email": "karthik.iyer@example.com",
        "headline": "Startups, contracts and company law", "experience_years": 11, "consultation_fee": 2000,
        "specialisations": ["Corporate & business", "Intellectual property", "Labour & employment"], "languages": ["English", "Tamil", "Hindi"],
        "courts": ["NCLT Bengaluru"], "locality": "Koramangala", "education": "BA LLB (Hons), NALSAR",
        "bar_enrolment": "KAR/1630/2014", "weekly_hours": {d: [["09:00", "12:00"]] for d in ("mon", "tue", "wed", "thu", "fri", "sat")},
        "bio": "Karthik advises founders on incorporation, shareholder agreements, ESOPs, trademarks and employment contracts.",
    },
    {
        "name": "Adv. Lakshmi Narayan", "email": "lakshmi.narayan@example.com",
        "headline": "Cheque bounce, recovery and criminal defence", "experience_years": 17, "consultation_fee": 1000,
        "specialisations": ["Criminal", "Cheque bounce", "Banking & recovery"], "languages": ["English", "Kannada", "Tamil"],
        "courts": ["Magistrate Courts, Bengaluru", "Sessions Court, Bengaluru"], "locality": "Malleshwaram", "education": "LLB, KLE Law College",
        "bar_enrolment": "KAR/0877/2008", "weekly_hours": {**WEEKDAYS_10_TO_6, "sat": [["10:00", "14:00"]]},
        "bio": "Lakshmi takes Section 138 cheque bounce cases for both complainants and accused, bail matters and loan recovery disputes.",
    },
    {
        "name": "Adv. Rohan Mehta", "email": "rohan.mehta@example.com",
        "headline": "Tax notices, GST and cyber fraud", "experience_years": 6, "consultation_fee": 800,
        "specialisations": ["Tax", "Cyber crime", "Consumer protection"], "languages": ["English", "Hindi", "Marathi"],
        "courts": ["ITAT Bengaluru"], "locality": "Whitefield", "education": "BCom LLB, Symbiosis Law School",
        "bar_enrolment": "KAR/3011/2019", "weekly_hours": {d: [["18:00", "21:00"]] for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")},
        "bio": "Rohan replies to income tax and GST notices, and helps victims of online banking and UPI fraud file complaints and recover money.",
    },
]

def main() -> None:
    with SessionLocal() as db:
        agent = db.scalars(select(Role).where(Role.name == "agent")).one()
        for sample in SAMPLES:
            user = db.scalars(select(User).where(User.email == sample["email"])).first()
            if user is None:
                user = User(email=sample["email"], display_name=sample["name"], roles=[agent])
                db.add(user)
                db.flush()
            profile = db.get(LawyerProfile, user.id) or LawyerProfile(user_id=user.id, slug=sample["email"].split("@")[0].replace(".", "-"))
            for key, value in sample.items():
                if key not in ("name", "email"):
                    setattr(profile, key, value)
            profile.city, profile.is_listed = "Bengaluru", True
            db.add(profile)
        db.commit()
    print(f"{len(SAMPLES)} sample lawyers are listed at /lawyers.")

if __name__ == "__main__":
    main()
