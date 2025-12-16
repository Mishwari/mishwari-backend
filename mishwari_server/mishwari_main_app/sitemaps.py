"""SEO Sitemaps for Google indexing"""
from django.contrib.sitemaps import Sitemap
from django.contrib.sites.models import Site
from django.utils import timezone
from .models import Trip, CityList


class TripSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.9
    
    def get_urls(self, page=1, site=None, protocol=None):
        # Force correct domain for sitemap URLs
        site = Site(domain='yallabus.app', name='Yalla Bus')
        return super().get_urls(page=page, site=site, protocol='https')
    
    def items(self):
        return Trip.objects.filter(
            status='published'
        ).select_related('from_city', 'to_city', 'operator').order_by('-created_at')[:1000]
    
    def lastmod(self, obj):
        return obj.created_at
    
    def location(self, obj):
        return f'/bus_list/{obj.id}'


class CitySitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.7
    
    def get_urls(self, page=1, site=None, protocol=None):
        site = Site(domain='yallabus.app', name='Yalla Bus')
        return super().get_urls(page=page, site=site, protocol='https')
    
    def items(self):
        return CityList.objects.all().order_by('city')[:100]
    
    def location(self, obj):
        return f'/cities/{obj.city.lower()}'
