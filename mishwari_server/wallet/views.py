import time
from rest_framework import viewsets , status
from rest_framework.response import Response
from .models import Wallet, WalletTransaction
from .serializers import WalletTransactionSerializer, WalletSerializer
from django.contrib.auth.models import User
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny,IsAdminUser
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.generics import get_object_or_404




class WalletView(viewsets.ModelViewSet):
    # queryset = Wallet.objects.all()
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]    
    serializer_class = WalletSerializer
    
    def list(self, request, *args, **kwargs):
        wallet = get_object_or_404(Wallet, user=self.request.user)
        serializer = self.get_serializer(wallet)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['POST'], url_path='add-funds')
    def add_funds(self, request, pk=None):
        wallet = self.get_object()
        amount = request.data.get('amount',0)
        if amount <= 0: # could allow 0 amount for free trips
            return Response({'message': 'Amount must be greater than 0'}, status=status.HTTP_400_BAD_REQUEST)
        wallet.balance += amount
        wallet.save()

        WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type='credit', # WalletTransaction.TYPE_ADD_FUNDS
            amount=amount
        )
        return Response({'message': 'Funds added successfully'}, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['POST'], url_path='wallet-deduct-funds')
    def deduct_funds(self, request, pk=None):
        print("Deduct Called")
        wallet = self.get_object()
        amount = request.data.get('amount',0)
        if amount <= 0:
            return Response({'message': 'Amount must be greater than 0'}, status=status.HTTP_400_BAD_REQUEST)
        if wallet.balance < amount:
            return Response({'message': 'Insufficient funds'}, status=status.HTTP_400_BAD_REQUEST)
        wallet.balance -= amount
        wallet.save()

        WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type='debit', #WalletTransaction.TYPE_DEDUCT_FUNDS
            amount=amount
        )
        return Response({'message': 'Funds deducted successfully'}, status=status.HTTP_200_OK)
    
    
class WalletTransactionView(viewsets.ModelViewSet):
    
    # queryset = WalletTransaction.objects.all()
    serializer_class = WalletTransactionSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get_queryset(self):
        # time.sleep(2) # to test the skeleton
        return WalletTransaction.objects.filter(wallet__user = self.request.user.id)
    

