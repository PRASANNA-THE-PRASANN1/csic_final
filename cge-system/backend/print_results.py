import json

data = json.load(open('test_comprehensive_results.json'))
print(f"TOTAL: {data['total']}, PASS: {data['passed']}, FAIL: {data['failed']}, SKIP: {data['skipped']}")
print(f"Pass Rate: {data['pass_rate']}")
print()

current_section = None
for r in data['results']:
    if r['section'] != current_section:
        current_section = r['section']
        print(f"\n--- {current_section} ---")
    symbol = 'PASS' if r['passed'] else ('FAIL' if r['passed'] is False else 'SKIP')
    detail = r['detail'][:100] if r['detail'] else ''
    print(f"  {symbol:4s} | {r['test']}")
    if detail:
        print(f"         {detail}")

print("\n\n=== FAILURES ===")
for r in data['results']:
    if r['passed'] is False:
        print(f"  [{r['section']}] {r['test']}")
        print(f"    Detail: {r['detail']}")
