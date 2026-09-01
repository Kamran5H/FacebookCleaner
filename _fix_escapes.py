"""Binary-safe replace of literal backslash-quote in the file."""
from pathlib import Path

target = Path(r"C:\Users\chkam\OneDrive\Desktop\BrandFinder\FacebookCleaner\backend\fb_engine.py")
data = target.read_bytes()
# Find all 0x5C 0x27 pairs
positions = []
i = 0
while i < len(data) - 1:
    if data[i] == 0x5C and data[i + 1] == 0x27:
        positions.append(i)
    i += 1

print(f"Found {len(positions)} occurrences of backslash-quote")
print("Sample positions:", positions[:5])
if positions:
    for p in positions[:3]:
        print(f"  At {p}: {data[max(0,p-10):p+12]!r}")

# Replace 0x5C 0x27 with 0x27
new_data = bytes(b if not (b == 0x5C and i + 1 < len(data) and data[i + 1] == 0x27) else None
                  for i, b in enumerate(data))
# Simpler: just do bytes translation
out = bytearray()
i = 0
while i < len(data):
    if i < len(data) - 1 and data[i] == 0x5C and data[i + 1] == 0x27:
        out.append(0x27)
        i += 2
    else:
        out.append(data[i])
        i += 1

target.write_bytes(bytes(out))
print(f"Wrote {len(out)} bytes (was {len(data)})")
