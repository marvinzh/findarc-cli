__all__ = ["cli"]


def __getattr__(name: str):
    if name == "cli":
        from .main import cli

        return cli
    raise AttributeError(name)
