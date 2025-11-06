from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import WalletView,WalletTransactionView

router = DefaultRouter()
router.register(r'balance', WalletView, basename='balance')

router.register(r'transactions', WalletTransactionView, basename='transactions')

urlpatterns = [
    path('wallet/', include(router.urls)),
]