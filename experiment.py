from math import isqrt

def factor_semiprime(n):
    for p in range(2, isqrt(n) + 1):
        if n % p == 0:
            q = n // p
            # We want two distinct primes.
            if p != q and is_prime(p) and is_prime(q):
                return p, q
    return None

def is_prime(n):
    if n < 2:
        return False
    for p in range(2, isqrt(n) + 1):
        if n % p == 0:
            return False
    return True

for nbits in range(2, 11):
    valid = []
    for n in range(2**nbits):
        factors = factor_semiprime(n)
        if factors:
            valid.append((n, factors))

    print(f"{nbits:2d} bits: {len(valid):4d} semiprimes")
    print("   ", valid[:10])
