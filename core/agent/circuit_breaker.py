import asyncio, time, logging

class CircuitBreaker:
    '''LLM circuit breaker: trip after N consecutive failures, half-open after cooldown'''
    def __init__(self, name='llm', max_failures=3, cooldown=30, half_open_max=1):
        self.name = name
        self.max_failures = max_failures
        self.cooldown = cooldown
        self.half_open_max = half_open_max
        self.state = 'closed'
        self.failures = 0
        self.last_failure = 0.0
        self.half_open_tries = 0

    async def call(self, fn, fallback=None, *args, **kw):
        now = time.time()
        if self.state == 'open':
            if now - self.last_failure >= self.cooldown:
                self.state = 'half-open'
                self.half_open_tries = 0
                logging.info(f'[CB:{self.name}] open->half-open')
            else:
                logging.warning(f'[CB:{self.name}] open, returning fallback')
                return fallback() if callable(fallback) else fallback
        try:
            result = await fn(*args, **kw)
            if self.state == 'half-open':
                self.half_open_tries += 1
                if self.half_open_tries >= self.half_open_max:
                    self.state = 'closed'
                    self.failures = 0
                    logging.info(f'[CB:{self.name}] half-open->closed')
            return result
        except Exception as e:
            self.failures += 1
            self.last_failure = now
            if self.failures >= self.max_failures:
                self.state = 'open'
                logging.warning(f'[CB:{self.name}] closed->open ({self.failures} failures)')
            if fallback is not None:
                return fallback() if callable(fallback) else fallback
            raise e

    def reset(self):
        self.state = 'closed'
        self.failures = 0
        self.half_open_tries = 0
        logging.info(f'[CB:{self.name}] reset')

    @property
    def is_available(self):
        if self.state == 'open':
            return time.time() - self.last_failure >= self.cooldown
        return True
