from pathlib import Path
from math import isqrt


def is_prime(n):
    if n < 2:
        return False
    for p in range(2, isqrt(n) + 1):
        if n % p == 0:
            return False
    return True


def factor_semiprime(n):
    for p in range(2, isqrt(n) + 1):
        if n % p == 0:
            q = n // p
            if p != q and is_prime(p) and is_prime(q):
                return p, q
    return None


N = 4
inputs = [f"x{i}" for i in range(N)]

# One .names node per output bit.
outputs = (
    [f"p{i}" for i in range(N - 1, -1, -1)] +
    [f"q{i}" for i in range(N - 1, -1, -1)]
)

lines = [
    ".model factor4",
    ".inputs " + " ".join(inputs),
    ".outputs " + " ".join(outputs),
    "",
]

# Each output is specified independently.
#
# For each output bit, list the input patterns for which
# that bit must be 1. Everything else is don't-care.
for output_index, output_name in enumerate(outputs):
    ones = []

    for n in range(2**N):
        factors = factor_semiprime(n)
        if factors is None:
            continue

        p, q = factors
        value = p if output_name.startswith("p") else q
        bit = int(output_name[1:])
        
        if (value >> bit) & 1:
            pattern = format(n, f"0{N}b")
            ones.append(pattern)

    lines.append(f".names {' '.join(inputs)} {output_name}")
    for pattern in ones:
        lines.append(f"{pattern} 1")
    lines.append("")

lines.append(".end")

Path("factor4.blif").write_text("\n".join(lines))

print(Path("factor4.blif").read_text())
