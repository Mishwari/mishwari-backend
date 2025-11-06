from django.db import models
from django.contrib.auth.models import User



class Wallet(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    # currency = models.CharField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.user.username}'s wallet: {self.balance}"
    

class WalletTransaction(models.Model):
    TRANSACTION_TYPE = (
        ('credit', 'credit'),
        ('debit', 'debit'),
    )

    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="wallet_transactions")
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    title = models.CharField(max_length=16, null=False, blank=False, default='unknown')
    description = models.TextField(blank=True, max_length=150)
    reference_id = models.CharField(max_length=32, default='unknown')
    timestamp = models.DateTimeField(auto_now_add=True)



    def __str__(self):
        return f"{self.wallet.user.username} {self.transaction_type} of {self.amount} on {self.timestamp}"