from django.urls import path, include
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.sitemaps.views import sitemap
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from mishwari_main_app.sitemaps import TripSitemap, CitySitemap

sitemaps = {
    'trips': TripSitemap,
    'cities': CitySitemap,
}

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include("mishwari_main_app.urls")),
    path('api/', include("wallet.urls")),
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='django.contrib.sitemaps.views.sitemap'),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)