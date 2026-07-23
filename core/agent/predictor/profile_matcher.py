class ProfileMatcher:
    async def match(self, action_type, action_summary, profile):
        patterns = profile.get("preferred_patterns", [])
        if not patterns: return 0.0
        matched = 0
        for p in patterns:
            if p.get("type") == action_type: matched += 1
            if p.get("action", "") in action_summary: matched += 1
        return min(1.0, matched / (len(patterns) * 2)) if patterns else 0.0