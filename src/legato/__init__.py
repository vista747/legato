from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import tomllib

__all__ = ["__version__", "__status__"]
__status__ = "beta"

try:
	__version__ = version("legato-fm")
except PackageNotFoundError:
	try:
		pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
		data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
		__version__ = str((data.get("project") or {}).get("version") or "0.0.0")
	except Exception:
		__version__ = "0.0.0"
