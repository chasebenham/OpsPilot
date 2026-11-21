from decimal import Decimal
from datetime import datetime, timedelta, time, timezone
from zoneinfo import ZoneInfo

POLICY_VERSION = 'meridian-2026-01'
ROUTES = {'IT Incident': 'IT', 'Purchase Request': 'Finance', 'Cross-Department Project': 'Operations'}
BUSINESS_ZONE = ZoneInfo('America/Phoenix')

def approval_stages(amount: Decimal, currency: str):
    if currency != 'USD': raise ValueError('Only USD is supported by this policy')
    if not amount.is_finite() or amount <= 0: raise ValueError('A positive total commitment is required')
    stages = ['Department Manager']
    if amount >= Decimal('1000'): stages.append('Finance Approver')
    if Decimal('5000') <= amount < Decimal('20000'): stages.append('Operations Director')
    if amount >= Decimal('20000'): stages.append('Executive Approver')
    return stages

def business_deadline(start: datetime, duration: timedelta) -> datetime:
    if start.tzinfo is None: raise ValueError('An aware UTC datetime is required')
    current = start.astimezone(BUSINESS_ZONE)
    while duration > timedelta(0):
        if current.weekday() >= 5:
            current = datetime.combine(current.date() + timedelta(days=7-current.weekday()), time(9), BUSINESS_ZONE)
            continue
        opening = datetime.combine(current.date(), time(9), BUSINESS_ZONE)
        closing = datetime.combine(current.date(), time(17), BUSINESS_ZONE)
        if current < opening: current = opening
        if current >= closing:
            current = datetime.combine(current.date() + timedelta(days=1), time(9), BUSINESS_ZONE)
            continue
        available = closing - current
        if duration <= available: return (current + duration).astimezone(timezone.utc)
        duration -= available
        current = datetime.combine(current.date() + timedelta(days=1), time(9), BUSINESS_ZONE)
    return current.astimezone(timezone.utc)

def response_deadline(start: datetime, priority: str) -> datetime:
    if start.tzinfo is None: raise ValueError('An aware UTC datetime is required')
    if priority == 'Critical': return (start + timedelta(minutes=15)).astimezone(timezone.utc)
    if priority == 'High': return (start + timedelta(hours=1)).astimezone(timezone.utc)
    if priority == 'Normal': return business_deadline(start, timedelta(hours=4))
    if priority == 'Low': return business_deadline(start, timedelta(hours=8))
    raise ValueError('Unknown priority')
