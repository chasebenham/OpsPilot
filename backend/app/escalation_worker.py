"""Run once or periodically in a dedicated local worker: python -m app.escalation_worker --watch."""
import argparse
import time
from .models import SessionLocal
from .workflows import evaluate_all

def run():
    with SessionLocal() as db:
        count=evaluate_all(db); db.commit(); print(f'Evaluated {count} incident(s).', flush=True)
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--watch',action='store_true');parser.add_argument('--interval',type=int,default=60);args=parser.parse_args()
    if args.interval<10: parser.error('Interval must be at least 10 seconds')
    while True:
        try: run()
        except Exception as exc:
            print(f'Evaluation failed: {type(exc).__name__}',flush=True)
            if not args.watch: raise
        if not args.watch: break
        time.sleep(args.interval)
if __name__=='__main__': main()
