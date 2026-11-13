from django.core.mail.backends.base import BaseEmailBackend


class RedactedConsoleBackend(BaseEmailBackend):
    """Development simulation: never print recipient, code, body or headers."""

    def send_messages(self, email_messages):
        messages = list(email_messages or [])
        if messages:
            print("[YIPPEE development email simulation: message content hidden]")
        return len(messages)
