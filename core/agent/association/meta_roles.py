from .models import MetaRole

class MetaRoles:
    ALL = list(MetaRole)
    DOMAIN_MAP = {
        "physical": [MetaRole.SOURCE, MetaRole.SINK, MetaRole.DISSIPATE, MetaRole.STORE_P, MetaRole.STORE_K, MetaRole.TRANSFORM, MetaRole.JSUM, MetaRole.JSPLIT],
        "software": [MetaRole.SOURCE, MetaRole.SINK, MetaRole.STORE_P, MetaRole.STORE_K, MetaRole.DISSIPATE, MetaRole.TRANSFORM, MetaRole.JSUM, MetaRole.JSPLIT],
        "general": list(MetaRole),
    }
    @classmethod
    def domain_roles(cls, domain):
        return cls.DOMAIN_MAP.get(domain, cls.DOMAIN_MAP["general"])