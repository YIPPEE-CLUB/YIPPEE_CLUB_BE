"""SQL-blocked review of bootstrap settings; never applies migrations."""
from copy import deepcopy

from .user_model_prepare import *  # noqa: F403

USER_MODEL_OFFLINE_PREVIEW = True
DATABASES = deepcopy(DATABASES)  # noqa: F405
DATABASES["default"]["ENGINE"] = "config.offline_mysql"
