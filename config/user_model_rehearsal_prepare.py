"""Legacy auth.User on the isolated rehearsal instance."""
from .user_model_rehearsal import *  # noqa: F403

AUTH_USER_MODEL = "auth.User"
