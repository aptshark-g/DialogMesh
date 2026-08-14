def is_prime(n):
    """判断 n 是否为质数"""
    if n < 2:
        return False
    for i in range(2, int(n ** 0.5) + 1):
        if n % i == 0:
            return False
    return True


def sum_primes_up_to(n):
    """计算 1 到 n 之间所有质数的和"""
    return sum(x for x in range(1, n + 1) if is_prime(x))


if __name__ == '__main__':
    result = sum_primes_up_to(100)
    primes = [x for x in range(1, 101) if is_prime(x)]
    print(f"1 到 100 之间的质数: {primes}")
    print(f"质数个数: {len(primes)} 个")
    print(f"质数之和: {result}")
