class CandidateGenerator:
    def __init__(self, llm_provider, max_retries=1):
        self.llm = llm_provider
        self.max_retries = max_retries

    async def generate(self, chain_summary, profile, graph_hints):
        prompt = self._build_prompt(chain_summary, profile, graph_hints)
        for _ in range(self.max_retries + 1):
            raw = await self.llm.generate(prompt, max_tokens=200)
            parsed = self._parse(raw)
            if parsed: return parsed
        return []

    def _build_prompt(self, chain, profile, hints):
        prompt = "You are analyzing a system administrator and developer's behavior.\n"
        prompt += "Recent behavior chain: " + chain
        if hints:
            prompt += "\nPossible next steps from history: " + str(hints)
        prompt += "\nGenerate 3-5 most likely NEXT actions (technical/system operations only) with probability [0,1]."
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
