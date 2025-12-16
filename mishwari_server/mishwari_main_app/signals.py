from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db.models import Avg
from .models import TripReview, Bus, Driver, BusOperator, Trip
from .utils.google_indexing import notify_google_indexing
import os
import urllib.request
import urllib.error

@receiver(post_save, sender=TripReview)
def update_ratings_on_review(sender, instance, created, **kwargs):
    """Auto-update cached ratings when review is created"""
    if not created:
        return
    
    # Update Bus rating
    if instance.bus_snapshot:
        bus_reviews = TripReview.objects.filter(bus_snapshot=instance.bus_snapshot)
        avg = bus_reviews.aggregate(Avg('bus_condition_rating'))['bus_condition_rating__avg']
        instance.bus_snapshot.avg_rating = round(avg, 2) if avg else 0.00
        instance.bus_snapshot.total_reviews = bus_reviews.count()
        instance.bus_snapshot.save(update_fields=['avg_rating', 'total_reviews'])
    
    # Update Driver rating
    if instance.driver_snapshot:
        driver_reviews = TripReview.objects.filter(driver_snapshot=instance.driver_snapshot)
        avg = driver_reviews.aggregate(Avg('driver_rating'))['driver_rating__avg']
        instance.driver_snapshot.driver_rating = round(avg, 2) if avg else 0.00
        instance.driver_snapshot.total_reviews = driver_reviews.count()
        instance.driver_snapshot.save(update_fields=['driver_rating', 'total_reviews'])
    
    # Update Operator rating
    operator_reviews = TripReview.objects.filter(operator_snapshot=instance.operator_snapshot)
    avg = operator_reviews.aggregate(Avg('overall_rating'))['overall_rating__avg']
    instance.operator_snapshot.avg_rating = round(avg, 2) if avg else 0.00
    instance.operator_snapshot.total_reviews = operator_reviews.count()
    instance.operator_snapshot.save(update_fields=['avg_rating', 'total_reviews'])
    
    # Recalculate health score
    from .models import OperatorMetrics
    metrics, created = OperatorMetrics.objects.get_or_create(operator=instance.operator_snapshot)
    metrics.recalculate_health_score()


@receiver(post_save, sender=Trip)
def update_health_score_on_trip_change(sender, instance, created, **kwargs):
    """Recalculate health score when trip is cancelled and notify Google for indexing"""
    
    # Auto-submit to Google when trip is published
    if instance.status == 'published':
        site_url = os.getenv('SITE_URL', 'https://yallabus.app')
        trip_url = f'{site_url}/bus_list/{instance.id}'
        notify_google_indexing(trip_url, 'URL_UPDATED')
        
        # Ping Google about sitemap update
        try:
            urllib.request.urlopen(f'http://www.google.com/ping?sitemap={site_url}/sitemap.xml', timeout=2)
            print(f'[SITEMAP] Pinged Google about sitemap update')
        except (urllib.error.URLError, Exception) as e:
            print(f'[SITEMAP] Failed to ping Google: {str(e)}')
    
    # Notify Google when trip is cancelled (remove from index)
    if instance.status == 'cancelled':
        site_url = os.getenv('SITE_URL', 'https://yallabus.app')
        trip_url = f'{site_url}/bus_list/{instance.id}'
        notify_google_indexing(trip_url, 'URL_DELETED')
        
        from .models import OperatorMetrics
        metrics, created = OperatorMetrics.objects.get_or_create(operator=instance.operator)
        
        # Update cancellation rate
        total_trips = Trip.objects.filter(operator=instance.operator).count()
        cancelled_trips = Trip.objects.filter(operator=instance.operator, status='cancelled').count()
        
        if total_trips > 0:
            metrics.cancellation_rate = (cancelled_trips / total_trips) * 100
            metrics.save(update_fields=['cancellation_rate'])
        
        metrics.recalculate_health_score()
