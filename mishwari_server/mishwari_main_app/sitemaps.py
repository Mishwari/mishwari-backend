"""SEO Sitemaps for Google indexing"""
from django.contrib.sitemaps import Sitemap
from django.utils import timezone
from .models import Trip, CityList


class TripSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.9
    protocol = 'https'
    
    def get_domain(self):
        return 'yallabus.app'
    
    def items(self):
        # Return all trips for testing, filter by published status in production
        return Trip.objects.select_related('from_city', 'to_city', 'operator').order_by('-created_at')[:100]
    
    def lastmod(self, obj):
        return obj.created_at
    
    def location(self, obj):
        return f'/bus_list/{obj.id}'


class CitySitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.7
    protocol = 'https'
    
    def get_domain(self):
        return 'yallabus.app'
    
    def items(self):
        return CityList.objects.all().order_by('city')[:100]
    
    def location(self, obj):
        return f'/cities/{obj.city.lower()}'
