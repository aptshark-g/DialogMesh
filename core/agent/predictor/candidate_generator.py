class CandidateGenerator:
    DEFAULT_DOMAIN = (
        "You are analyzing a user's recent behavior in a personal AI assistant "
        "conversation, predicting the user's most likely next action."
    )

    def __init__(self, llm_provider, max_retries=1, domain_prompt=None):
        self.llm = llm_provider
        self.max_retries = max_retries
        self.domain_prompt = domain_prompt or self.DEFAULT_DOMAIN

    async def generate(self, chain_summary, profile, graph_hints):
        if self.llm is None:
            return []
        prompt = self._build_prompt(chain_summary, profile, graph_hints)
        for _ in range(self.max_retries + 1):
            raw = await self.llm.generate(prompt, max_tokens=200)
            parsed = self._parse(raw)
            if parsed: return parsed
        return []

    def _build_prompt(self, chain, profile, hints):
        prompt = self.domain_prompt + "\n"
        prompt += "Recent behavior chain: " + chain
        if hints:
            prompt += "\nPossible next steps from history: " + str(hints)
        prompt += "\nGenerate 3-5 most likely NEXT actions with probability [0,1]."
        prompt += "\n[{\"action\": \"...\", \"probability\": 0.xx}]"
        return prompt

    def _parse(self, raw):
        import json
        start, end = raw.find("["), raw.rfind("]")
        if start == -1 or end == -1: return None
        try:
            data = json.loads(raw[start:end+1])
            return [(d["action"], max(0, min(1, float(d["probability"])))) for d in data]
        except: return None
