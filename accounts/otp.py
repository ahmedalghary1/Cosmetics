from abc import ABC, abstractmethod


class OTPProvider(ABC):
    """Provider boundary for adding SMS OTP without coupling authentication to a vendor."""

    @abstractmethod
    def send(self, phone, code):
        raise NotImplementedError


class DisabledOTPProvider(OTPProvider):
    def send(self, phone, code):
        raise RuntimeError("SMS OTP is not configured. Password reset by email remains available.")
