"""All Jobgent errors. Every error carries enough context to act on."""


class JobgentError(Exception):
    """Base class for errors raised by Jobgent."""


class MissingSecretError(JobgentError):
    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(
            f"{name} is not set. Put it in the environment or in ~/.config/secrets/env "
            f"as {name}=... and retry."
        )


class SourceError(JobgentError):
    def __init__(self, source: str, message: str) -> None:
        self.source = source
        super().__init__(f"[{source}] {message}")


class ProfileNotVerifiedError(JobgentError):
    def __init__(self) -> None:
        super().__init__(
            "The profile is not verified yet. Review profile.yaml (profile_get), fix anything "
            "wrong with profile_update, then call profile_set_verified(true). "
            "Nothing is generated from unverified facts."
        )


class InventedClaimError(JobgentError):
    def __init__(self, claims: list[str]) -> None:
        self.claims = claims
        joined = "; ".join(claims)
        super().__init__(f"Generated text contains claims not supported by the profile: {joined}")


class LLMError(JobgentError):
    def __init__(self, message: str, raw: str) -> None:
        self.raw = raw
        super().__init__(f"{message}. Raw model output: {raw[:500]}")
