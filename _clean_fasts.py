"""One-shot: inspect and clean bad facts in Plasma memory.

Usage:
    python _clean_facts.py          # list everything
    python _clean_facts.py delete   # interactive cleanup
"""
import sys
from backend.modules.memory.store import MemoryStore


def main():
    mem = MemoryStore()
    facts = mem.get_facts(limit=500)
    print(f"\nTotal facts: {len(facts)}\n")
    for f in facts:
        print(f"  id={f['id']:3d}  [{f['category']:12s}]  {f['content']}")

    if len(sys.argv) > 1 and sys.argv[1] == "delete":
        print()
        for f in facts:
            resp = input(
                f"Delete id={f['id']} '{f['content'][:60]}'? [y/N/q] "
            ).strip().lower()
            if resp == "q":
                break
            if resp == "y":
                mem.delete_fact(f["id"])
                print(f"  deleted id={f['id']}")


if __name__ == "__main__":
    main()