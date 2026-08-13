def is_prime(n: int) -> bool:
    """判断 n 是否为质数（n >= 2）"""
    if n < 2:
        return False
    if n == 2:
        return True
    if n % 2 == 0:
        return False
    i = 3
    while i * i <= n:
        if n % i == 0:
            return False
        i += 2
    return True

def main():
    primes = [n for n in range(1, 101) if is_prime(n)]
    total = sum(primes)
    print("1 到 100 的质数列表:", primes)
    print("质数个数:", len(primes))
    print("质数之和:", total)

if __name__ == "__main__":
    main()
