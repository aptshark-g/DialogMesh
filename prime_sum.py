def is_prime(n: int) -> bool:
    """判断 n 是否为质数（n > 1，且只能被 1 和自身整除）"""
    if n < 2:
        return False
    for i in range(2, int(n ** 0.5) + 1):
        if n % i == 0:
            return False
    return True

def main():
    primes = [n for n in range(1, 101) if is_prime(n)]
    total = sum(primes)
    print("1 到 100 之间的质数：", primes)
    print("质数个数：", len(primes))
    print("质数之和：", total)

if __name__ == "__main__":
    main()
