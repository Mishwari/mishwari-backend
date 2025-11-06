from abc import ABC, abstractmethod

class PaymentGateway(ABC):
    @abstractmethod
    def initiate_payment(self, booking):
        pass

    @abstractmethod
    def handle_webhook(self, request):
        pass


