def is_prime(n: int) -> bool:
    """判断 n 是否为质数（质数定义：大于 1 且只能被 1 和自身整除）"""
    if n < 2:
        return False
    for i in range(2, int(n ** 0.5) + 1):
        if n % i == 0:
            return False
    return True


def sum_primes(limit: int):
    """返回 1 到 limit 之间所有质数的列表及其和"""
    primes = [n for n in range(2, limit + 1) if is_prime(n)]
    return primes, sum(primes)


if __name__ == "__main__":
    LIMIT = 100
    primes, total = sum_primes(LIMIT)
    print(f"1 到 {LIMIT} 之间的质数: {primes}")
    print(f"质数个数: {len(primes)}")
    print(f"质数之和: {total}")
