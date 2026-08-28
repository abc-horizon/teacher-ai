"""T1.4 CLI wrapper: download pending submission files from Moodle and
extract their text into the local project database.

All actual logic lives in app/extractor/importer.py (shared with the portal
pages) — this script is only a thin command-line entry point for manual /
admin use.

Terminal-output rule: never print MOODLE_TOKEN, a student identity, or any
extracted submission text. The summary below reports counts and failure
*types* only.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.extractor.importer import extract_pending_files


def main():
    print("=== استخراج نص ملفات التسليمات المعلَّقة (pending) ===\n")
    counters, failure_reasons = extract_pending_files()

    print("=== الملخص ===")
    print(f"نجح الاستخراج: {counters['success']}")
    print(f"فشل الاستخراج: {counters['failed']}")
    if failure_reasons:
        print("أسباب الفشل (مجمّعة حسب نوع الخطأ فقط):")
        for reason, count in sorted(failure_reasons.items()):
            print(f"  - {reason}: {count}")


if __name__ == "__main__":
    main()
