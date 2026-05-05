import json
from pathlib import Path
from typing import Any
from datetime import date

from sqlalchemy.orm import Session

from app.models.persistence import IntegrationOutbox, VerificationRequest, VerificationResult, VerificationWorkItem
from app.services.persistence_service import patient_key_for_row


SEED_PATH = Path('data/demo_seed.json')


def _load_seed() -> dict[str, Any]:
    return json.loads(SEED_PATH.read_text(encoding='utf-8'))


def load_demo_data(db: Session) -> dict:
    seed = _load_seed()
    stats = {"work_items": {"inserted": 0, "skipped": 0}, "requests": {"inserted": 0, "skipped": 0}, "results": {"inserted": 0, "skipped": 0}, "outbox": {"inserted": 0, "skipped": 0}}
    for row in seed.get('work_items', []):
        key = patient_key_for_row(row['first_name'], row['last_name'], date.fromisoformat(row['dob']), row['member_id'], row['payer_id'])
        existing = db.query(VerificationWorkItem).filter(VerificationWorkItem.patient_key == key).first()
        if existing:
            stats['work_items']['skipped'] += 1
            continue
        payload = {k: v for k, v in row.items() if k != 'patient_key'}
        payload['dob'] = date.fromisoformat(payload['dob'])
        payload['validation_status'] = 'pending_validation'
        payload['needs_validation'] = True
        payload['last_validated_at'] = None
        payload['last_request_id'] = None
        payload['last_error_message'] = None
        item = VerificationWorkItem(patient_key=key, is_demo=True, **payload)
        db.add(item)
        stats['work_items']['inserted'] += 1
    db.commit()
    return stats


def delete_demo_data(db: Session) -> dict:
    outbox = db.query(IntegrationOutbox).filter(IntegrationOutbox.is_demo.is_(True)).delete()
    results = db.query(VerificationResult).filter(VerificationResult.is_demo.is_(True)).delete()
    reqs = db.query(VerificationRequest).filter(VerificationRequest.is_demo.is_(True)).delete()
    items = db.query(VerificationWorkItem).filter(VerificationWorkItem.is_demo.is_(True)).delete()
    db.commit()
    return {"outbox": outbox, "results": results, "requests": reqs, "work_items": items}


def demo_data_counts(db: Session) -> dict:
    def c(model):
        d = db.query(model).filter(model.is_demo.is_(True)).count()
        n = db.query(model).filter(model.is_demo.is_(False)).count()
        return {"demo": d, "non_demo": n}
    return {
        'work_items': c(VerificationWorkItem),
        'requests': c(VerificationRequest),
        'results': c(VerificationResult),
        'outbox': c(IntegrationOutbox),
    }
